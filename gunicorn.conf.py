import multiprocessing
import os

bind = "127.0.0.1:8000"
workers = max(2, multiprocessing.cpu_count() // 2)
threads = 2
worker_class = "gthread"
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
preload_app = True
