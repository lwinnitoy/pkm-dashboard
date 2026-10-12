"""The built-frontend route (single-port deploys): files from dist, else index.html,
and never anything outside dist."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


@pytest.fixture()
def spa(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>INDEX")
    (dist / "favicon.svg").write_text("<svg/>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.env").write_text("SECRET=1")
    app = FastAPI()
    mount_frontend(app, dist)
    return TestClient(app)


def test_files_in_dist_are_served(spa):
    assert spa.get("/favicon.svg").text == "<svg/>"
    assert spa.get("/assets/app.js").text == "console.log(1)"


def test_unknown_paths_fall_back_to_the_spa(spa):
    assert spa.get("/").text.endswith("INDEX")
    assert spa.get("/net-worth").text.endswith("INDEX")


@pytest.mark.parametrize("path", ["/..%2Fsecret.env", "/%2E%2E%2Fsecret.env", "/assets/..%2F..%2Fsecret.env"])
def test_paths_escaping_dist_are_not_served(spa, path):
    resp = spa.get(path)
    assert "SECRET" not in resp.text


def test_api_paths_are_not_swallowed(spa):
    assert spa.get("/api/nope").status_code == 404
