import psutil

def print_celery_workers_resource_usage():
    print(f"{'PID':>7} {'CPU%':>6} {'MEM(MB)':>8} {'Name':>20} {'Cmdline'}")
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and isinstance(cmdline, list) and 'celery' in ' '.join(cmdline):
                cpu = proc.cpu_percent(interval=0.1)
                mem = proc.memory_info().rss / (1024 * 1024)
                print(f"{proc.info['pid']:>7} {cpu:>6.1f} {mem:>8.1f} {proc.info['name']:>20} {' '.join(cmdline)}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
            continue

if __name__ == "__main__":
    print_celery_workers_resource_usage()