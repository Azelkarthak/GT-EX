import multiprocessing
import traceback
import os

from BDD_Solutions.app import run as run_bdd
from GUnit_Solution.app import run as run_gunit
from Intelligent_Regression.app import run as run_ir

def safe_run(run_func, name):
    log_file = f"/tmp/{name.replace(' ', '_').lower()}.log"
    try:
        with open(log_file, 'a') as f:
            f.write(f"[{name}] Starting...\n")
            f.flush()
            run_func()
    except Exception as e:
        with open(log_file, 'a') as f:
            f.write(f"[{name}] Failed to start: {e}\n")
            f.write(traceback.format_exc())
            f.flush()

def launch_all():
    print("🚀 Launching all services...\n", flush=True)

    tasks = [
        ("BDD-Defect", run_bdd),
        ("GUnit", run_gunit),
        ("Intelligent Regression", run_ir)
    ]

    processes = []
    for name, func in tasks:
        p = multiprocessing.Process(target=safe_run, args=(func, name))
        p.start()
        processes.append(p)

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n🛑 Interrupt received, terminating all processes...", flush=True)
        for p in processes:
            p.terminate()
            p.join()

if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)  # Required for Linux
    launch_all()
