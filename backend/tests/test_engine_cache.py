"""The built engine saved once (when the image is built) and loaded at start-up (DECISIONS.md, decision 31)."""
import pickle

from feedforward.engine import cache, load_engine


def test_a_saved_engine_answers_like_the_built_one(tmp_path):
    built = load_engine()
    path = tmp_path / "engine.pkl"
    cache.save(built, path)
    loaded = cache.load(path)
    assert loaded is not None and loaded is not built
    assert len(loaded.foods) == len(built.foods)
    first = lambda rec: [f.food_id for f in rec.foods_for_goal("cognitive_function")[:10]]   # noqa: E731
    assert first(loaded) == first(built)


def test_a_file_from_other_code_or_data_is_ignored(tmp_path):
    path = tmp_path / "engine.pkl"
    path.write_bytes(pickle.dumps({"fingerprint": "made from older data", "engine": None}))
    assert cache.load(path) is None
    assert cache.load(tmp_path / "missing.pkl") is None


def test_runtime_caches_do_not_change_the_fingerprint(tmp_path, monkeypatch):
    """The Wikipedia and PubMed caches are written while the app runs; the engine does not read them."""
    assert all(name not in cache.FINGERPRINTED for name in ("wikipedia_cache.json", "pubmed_cache.json"))


def test_start_up_loads_the_saved_engine_instead_of_building(tmp_path, monkeypatch):
    import feedforward.engine as engine_module
    path = tmp_path / "engine.pkl"
    cache.save(load_engine(), path)
    monkeypatch.setenv("FEEDFORWARD_ENGINE_CACHE", str(path))

    def no_build(*_a, **_k):
        raise AssertionError("built instead of loaded")
    monkeypatch.setattr(engine_module, "build_engine", no_build)
    assert len(load_engine.__wrapped__().foods) == len(load_engine().foods)
