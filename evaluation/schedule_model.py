"""Wall-time model of the analysis schedule for 1 resume + N vacancies (E16). No model calls.

python -m evaluation.schedule_model [--facts 49] [--low 15] [--high 50] [--privacy 5] [--jobs 30]

Not a measurement: it replays stage latencies you give it (defaults: the figures reported for the
live run of 14 November) through two schedules and prints the median and p90 over random draws.
- now:      privacy → facts → W workers, each doing requirements → evaluation for one vacancy;
- overlap:  privacy → one pool of W slots; facts and every requirements call start at once, a
            vacancy's evaluation starts when its requirements and the facts are both ready.
`--scale` multiplies requirements/evaluation latencies and `--facts-scale` the facts latency, to
see what a shorter model output would buy. Replace the defaults with measured numbers before
quoting any result.
"""
import argparse
import heapq
import random
import statistics


def wall_time(workers, overlap, *, facts=49.0, low=15.0, high=50.0, privacy=5.0, jobs=30, scale=1.0,
              facts_scale=1.0, seed=0):
    rng = random.Random(seed)
    requirements = [rng.uniform(low, high) * scale for _ in range(jobs)]
    evaluation = [rng.uniform(low, high) * scale for _ in range(jobs)]
    facts *= facts_scale
    if not overlap:
        start = privacy + facts
        free = [start] * workers
        heapq.heapify(free)
        end = start
        for i in range(jobs):
            finished = heapq.heappop(free) + requirements[i] + evaluation[i]
            heapq.heappush(free, finished)
            end = max(end, finished)
        return end
    slots = [privacy] * workers
    heapq.heapify(slots)
    facts_done = heapq.heappop(slots) + facts
    heapq.heappush(slots, facts_done)
    ready = []
    for i in range(jobs):
        finished = heapq.heappop(slots) + requirements[i]
        heapq.heappush(slots, finished)
        ready.append((max(finished, facts_done), i))
    end = facts_done
    for at, i in sorted(ready):
        finished = max(heapq.heappop(slots), at) + evaluation[i]
        heapq.heappush(slots, finished)
        end = max(end, finished)
    return end


def summary(workers, overlap, runs=200, **kwargs):
    times = sorted(wall_time(workers, overlap, seed=seed, **kwargs) for seed in range(runs))
    return round(statistics.median(times)), round(times[int(0.9 * runs) - 1])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name, default in (('facts', 49.0), ('low', 15.0), ('high', 50.0), ('privacy', 5.0), ('scale', 1.0),
                          ('facts-scale', 1.0)):
        parser.add_argument('--' + name, type=float, default=default)
    parser.add_argument('--jobs', type=int, default=30)
    args = parser.parse_args(argv)
    kwargs = {'facts': args.facts, 'low': args.low, 'high': args.high, 'privacy': args.privacy, 'jobs': args.jobs,
              'scale': args.scale, 'facts_scale': args.facts_scale}
    print('schedule            workers  median, s  p90, s   (a model of the schedule, not a measurement)')
    for label, overlap in (('now', False), ('overlap', True)):
        for workers in (3, 6, 10, 16, args.jobs + 1):
            median, p90 = summary(workers, overlap, **kwargs)
            print(f'{label:18} {workers:8} {median:10} {p90:7}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
