# Folder: firetiger-demo/storage/cold_store.py
#
# Parquet file storage for historical data.
# Events are flushed from hot store to Parquet every 5 minutes.
# This is the "Iceberg-style" storage layer.
#
# Files are partitioned by time:
# data/events/year=2025/month=02/day=18/hour=15/part-xyz.parquet
#
# This partitioning means historical queries only read
# the relevant time range - fast even with months of data.

import pyarrow as pa
import pyarrow.parquet as pq
import os
import logging
from datetime import datetime
from typing import List
from ingestion.event_schema import EventSchema
import config

logger = logging.getLogger(__name__)

# PyArrow schema - must match EventSchema exactly
ARROW_SCHEMA = pa.schema([
    pa.field("timestamp",        pa.timestamp("ms")),
    pa.field("endpoint",         pa.string()),
    pa.field("method",           pa.string()),
    pa.field("status_code",      pa.int32()),
    pa.field("latency_ms",       pa.float64()),
    pa.field("db_query_count",   pa.int32()),
    pa.field("db_query_time_ms", pa.float64()),
    pa.field("user_id",          pa.string()),
    pa.field("session_id",       pa.string()),
    pa.field("memory_mb",        pa.float64()),
    pa.field("commit_sha",       pa.string()),
    pa.field("error_message",    pa.string()),
])


class ColdStore:
    """
    Parquet-based historical storage.
    
    Why Parquet?
    - Columnar format = fast analytical queries
    - Compressed = much smaller than CSV/JSON
    - Industry standard = can be queried by Snowflake, Athena, BigQuery
    - This is exactly how Apache Iceberg works under the hood
    
    In the video you can say:
    "Data lives in open Parquet files. Any tool that speaks 
    Iceberg can query this - Snowflake, Athena, even other AI agents."
    """
    
    def __init__(self):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        logger.info(f"ColdStore initialized at {config.DATA_DIR}")
    
    def _get_partition_path(self, dt: datetime) -> str:
        """
        Build the partition path for a given timestamp.
        Creates Hive-style partitioning: year=X/month=X/day=X/hour=X
        """
        path = os.path.join(
            config.DATA_DIR,
            f"year={dt.year}",
            f"month={dt.month:02d}",
            f"day={dt.day:02d}",
            f"hour={dt.hour:02d}"
        )
        os.makedirs(path, exist_ok=True)
        return path
    
    def flush(self, events: List[EventSchema]):
        """
        Write a batch of events to Parquet.
        Called every 5 minutes by the collector.
        Groups events by hour partition.
        """
        if not events:
            return
        
        # Group events by their hour partition
        partitions = {}
        for event in events:
            partition_path = self._get_partition_path(event.timestamp)
            if partition_path not in partitions:
                partitions[partition_path] = []
            partitions[partition_path].append(event)
        
        # Write each partition to its own file
        for partition_path, partition_events in partitions.items():
            self._write_partition(partition_path, partition_events)
        
        logger.info(f"Flushed {len(events)} events to {len(partitions)} partitions")
    
    def _write_partition(self, path: str, events: List[EventSchema]):
        """Write events to a single Parquet file in the partition directory"""
        
        # Convert events to columnar format for PyArrow
        data = {
            "timestamp":        [e.timestamp for e in events],
            "endpoint":         [e.endpoint for e in events],
            "method":           [e.method for e in events],
            "status_code":      [e.status_code for e in events],
            "latency_ms":       [e.latency_ms for e in events],
            "db_query_count":   [e.db_query_count for e in events],
            "db_query_time_ms": [e.db_query_time_ms for e in events],
            "user_id":          [e.user_id for e in events],
            "session_id":       [e.session_id for e in events],
            "memory_mb":        [e.memory_mb for e in events],
            "commit_sha":       [e.commit_sha for e in events],
            "error_message":    [e.error_message or "" for e in events],
        }
        
        table = pa.table(data, schema=ARROW_SCHEMA)
        
        # Filename includes timestamp to avoid collisions
        filename = f"part-{datetime.now().strftime('%H%M%S%f')}.parquet"
        filepath = os.path.join(path, filename)
        
        pq.write_table(table, filepath, compression="snappy")
    
    def read_historical(self, endpoint: str, hours_back: int) -> List[dict]:
        """
        Read historical events for an endpoint.
        Used by baseline engine to compute normal behavior over 7 days.
        Only reads relevant partitions - won't scan everything.
        """
        results = []
        now = datetime.now()
        
        for hours_ago in range(hours_back):
            dt = datetime.fromtimestamp(
                now.timestamp() - (hours_ago * 3600)
            )
            partition_path = self._get_partition_path(dt)
            
            if not os.path.exists(partition_path):
                continue
            
            # Read all parquet files in this partition
            for filename in os.listdir(partition_path):
                if not filename.endswith(".parquet"):
                    continue
                
                filepath = os.path.join(partition_path, filename)
                table = pq.read_table(
                    filepath,
                    filters=[("endpoint", "=", endpoint)]
                )
                
                results.extend(table.to_pylist())
        
        return results