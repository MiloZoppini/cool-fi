#!/usr/bin/env python3
"""Wrapper CI: esegue update_events.main() saltando il git push (lo gestisce il workflow)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import update_events as ue

ue._git_push = lambda repo_path: ue.log("  git push delegato al workflow GitHub Actions")
ue.main()
