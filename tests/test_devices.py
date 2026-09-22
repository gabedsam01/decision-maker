from decisors.devices import choose, probe_devices


def test_cpu_wins_when_it_is_faster() -> None:
    device, why = choose(
        [
            {"id": "cpu", "ok": True, "median_ms": 2.0},
            {"id": "cuda", "ok": True, "median_ms": 9.0},
        ]
    )
    assert device == "cpu"
    assert "processador" in why.lower()


def test_gpu_inside_noise_stays_on_cpu() -> None:
    device, _why = choose(
        [
            {"id": "cpu", "ok": True, "median_ms": 10.0},
            {"id": "cuda", "ok": True, "median_ms": 9.5},
        ]
    )
    assert device == "cpu"


def test_gpu_outside_noise_wins() -> None:
    device, _why = choose(
        [
            {"id": "cpu", "ok": True, "median_ms": 10.0},
            {"id": "cuda", "ok": True, "median_ms": 4.0},
        ]
    )
    assert device == "cuda"


def test_failed_gpu_is_not_recommended() -> None:
    device, _why = choose(
        [
            {"id": "cpu", "ok": True, "median_ms": 5.0},
            {"id": "cuda", "ok": False, "error": "RuntimeError"},
        ]
    )
    assert device == "cpu"


def test_parallel_only_when_two_candidates() -> None:
    def bench(device: str) -> dict[str, float]:
        return {"median_ms": 2.0 if device == "cpu" else 8.0, "p95_ms": 3.0, "reps": 7}

    one = probe_devices(bench, candidates=["cpu"])
    two = probe_devices(bench, candidates=["cpu", "cuda"])
    assert one["mode"] == "sequential"
    assert two["mode"] == "parallel"
    assert two["recommended"] == "cpu"
    assert one["lay"]
