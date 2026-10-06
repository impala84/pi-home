#!/usr/bin/env python3
"""Read-only Linux collector. JSONL, RSS/PSS rather than virtual address space."""
import argparse
import json
from pathlib import Path
import platform
import time
import urllib.request


def fields(path):
    values = {}
    for line in path.read_text().splitlines():
        key, _, value = line.partition(':')
        try: values[key] = int(value.split()[0])
        except (ValueError, IndexError): pass
    return values


def processes(proc=Path('/proc')):
    result = []
    for folder in proc.glob('[0-9]*'):
        try:
            command = (folder / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            category = 'bridge' if any(name in command for name in ('RoonBridge', 'RAATServer', 'RoonBridgeHelper')) else 'controller' if 'roon-controller/server.js' in command else 'gtk' if 'pi_bus_native.py' in command else 'api' if 'pi-bus-time-display --config' in command else 'compositor' if command.startswith(('cage ', '/usr/bin/cage ', 'seatd ', '/usr/bin/seatd ')) else None
            if category is None: continue
            status = fields(folder / 'status')
            pss = None
            try: pss = fields(folder / 'smaps_rollup').get('Pss')
            except OSError: pass
            result.append({'pid': int(folder.name), 'category': category, 'rss_kib': status.get('VmRSS'), 'pss_kib': pss})
        except OSError: pass
    return result


def cpu_counters():
    values = [int(value) for value in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(values), values[3] + values[4]


def snapshot(previous=None):
    memory = fields(Path('/proc/meminfo'))
    total, idle = cpu_counters()
    usage = None
    if previous and total > previous[0]: usage = 100 * (1 - (idle - previous[1]) / (total - previous[0]))
    thermals = {}
    for sensor in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        try: thermals[sensor.parent.name] = int(sensor.read_text()) / 1000
        except (OSError, ValueError): pass
    requests = {}
    for name, url in [('api', 'http://127.0.0.1:8765/api/status'), ('controller', 'http://127.0.0.1:8766/api/state')]:
        start = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=2) as response: response.read()
            requests[name] = {'ok': True, 'roundtrip_ms': (time.monotonic()-start)*1000}
        except OSError: requests[name] = {'ok': False}
    return {'epoch': time.time(), 'uptime_s': float(Path('/proc/uptime').read_text().split()[0]),
            'memory_kib': memory, 'used_excluding_reclaimable_kib': memory['MemTotal'] - memory.get('MemAvailable', memory.get('MemFree', 0)),
            'cpu_busy_percent': usage, 'temperature_c': thermals, 'processes': processes(),
            'local_http': requests, 'cpu_counters': [total, idle]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float, default=600)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--label', default='idle')
    args = parser.parse_args()
    if args.interval <= 0 or args.duration < 0: parser.error('Use positive interval and nonnegative duration')
    print(json.dumps({'metadata': {'os': platform.platform(), 'label': args.label, 'interval_s': args.interval}}), flush=True)
    deadline = time.monotonic() + args.duration
    previous = None
    while True:
        sample = snapshot(previous)
        previous = sample.pop('cpu_counters')
        print(json.dumps(sample), flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0: break
        time.sleep(min(args.interval, remaining))

if __name__ == '__main__': main()
