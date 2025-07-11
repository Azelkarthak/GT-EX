import multiprocessing
import time

from BDD_Solutions import run as run_bdd
from GUnit_Solution import run as run_gunit
from Intelligent_Regression import run as run_ir

def start_project(run_func, name):
    try:
        print(f"[{name}] Starting...")
        run_func()
    except Exception as e:
        print(f"[{name}] Failed to start: {e}")

if __name__ == "__main__":
    multiprocessing.freeze_support()  # <-- important on Windows
    print("🚀 Launching all projects...")

    processes = [
        multiprocessing.Process(target=start_project, args=(run_bdd, "BDD-Defect")),
        multiprocessing.Process(target=start_project, args=(run_gunit, "GUnit")),
        multiprocessing.Process(target=start_project, args=(run_ir, "Intelligent Regression")),
    ]

    for p in processes:
        p.start()

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down all projects...")
        for p in processes:
            p.terminate()
            p.join()
