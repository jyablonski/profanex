import time


def test_performance_sanity(profanity_filter_fixture):
    texts = ["You are a dumbass!"] * 1000
    start = time.perf_counter()
    for t in texts:
        profanity_filter_fixture.clean(t)
    duration = time.perf_counter() - start
    assert duration < 5, "Cleaning 1000 reviews took too long (>5s)"
