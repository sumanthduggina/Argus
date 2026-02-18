#!/bin/bash
# Root folder: firetiger-demo/run.sh
# Starts the entire system with one command.

echo "🔥 Starting Firetiger Demo..."

mkdir -p logs

# Start Flask app
echo "Starting Flask app on port 5000..."
python -m app.main > logs/app.log 2>&1 &
echo $! > app.pid
echo "✅ Flask app started (PID: $(cat app.pid))"

sleep 2

# Start agent (includes collector + detector)
echo "Starting agent..."
python main_agent.py &
echo $! > agent.pid
echo "✅ Agent started (PID: $(cat agent.pid))"

echo ""
echo "🟢 System running!"
echo "   Flask app:  http://localhost:5000/health"
echo "   Collector:  http://localhost:8001/health"
echo ""
echo "Next steps:"
echo "  1. python scripts/seed_db.py"
echo "  2. python scripts/run_load.py  (in new terminal)"
echo "  3. python scripts/verify_setup.py"
echo "  4. python scripts/simulate_bad_deploy.py  (to trigger demo)"
```

---

## Final Folder Structure Check
```
firetiger-demo/
├── .env
├── .gitignore
├── config.py
├── main_agent.py
├── run.sh
│
├── app/
│   ├── main.py
│   ├── middleware.py
│   └── db.py
│
├── ingestion/
│   ├── collector.py
│   └── event_schema.py
│
├── storage/
│   ├── hot_store.py
│   ├── cold_store.py
│   └── knowledge_graph.py
│
├── detection/
│   ├── baseline.py
│   └── detector.py
│
├── agent/
│   ├── orchestrator.py
│   ├── response_parser.py
│   └── steps/
│       ├── characterize.py
│       ├── hypothesize.py
│       ├── gather_evidence.py
│       ├── confirm.py
│       └── fix.py
│
├── actions/
│   ├── action_handler.py
│   ├── slack_notifier.py
│   ├── github_pr.py
│   ├── deployer.py
│   └── verifier.py
│
└── scripts/
    ├── seed_db.py
    ├── simulate_bad_deploy.py
    ├── simulate_good_deploy.py
    └── run_load.py
```

---

## Order to Paste Into Cursor
```
1.  config.py
2.  ingestion/event_schema.py       ← models first
3.  app/db.py
4.  app/middleware.py
5.  app/main.py
6.  storage/hot_store.py
7.  storage/cold_store.py
8.  storage/knowledge_graph.py
9.  ingestion/collector.py
10. detection/baseline.py
11. detection/detector.py
12. agent/response_parser.py
13. agent/steps/characterize.py
14. agent/steps/hypothesize.py
15. agent/steps/gather_evidence.py
16. agent/steps/confirm.py
17. agent/steps/fix.py
18. agent/orchestrator.py
19. actions/slack_notifier.py
20. actions/github_pr.py
21. actions/deployer.py
22. actions/verifier.py
23. actions/action_handler.py
24. scripts/seed_db.py
25. scripts/simulate_bad_deploy.py
26. scripts/simulate_good_deploy.py
27. scripts/run_load.py
28. main_agent.py
29. run.sh