"""Open a new empty show without ingesting clips first."""

from __future__ import annotations

import pytest

from backend.projects.open import open_show, rename_show


def test_open_show_persists_an_empty_named_project(env) -> None:
    body = open_show(env, title="  Cafe pickup  ")
    project_id = str(body["project_id"])
    try:
        assert body["title"] == "Cafe pickup"
        assert body["jobs"] == []
        assert body["health"] == "healthy"
        assert body["station_counts"] == {}
        stored = env.get_doc("pc-projects", project_id)
        assert stored is not None
        assert stored["title"] == "Cafe pickup"
        assert stored["project_id"] == project_id
    finally:
        env.delete_doc("pc-projects", project_id)


def test_open_show_defaults_untitled_when_title_is_blank(env) -> None:
    body = open_show(env, title="   ")
    project_id = str(body["project_id"])
    try:
        assert body["title"] == "Untitled show"
        assert project_id.startswith("show-")
    finally:
        env.delete_doc("pc-projects", project_id)


def test_rename_show_updates_the_stored_title(env) -> None:
    body = open_show(env, title="Cafe pickup")
    project_id = str(body["project_id"])
    try:
        renamed = rename_show(env, project_id, title="  Night exteriors  ")
        assert renamed["title"] == "Night exteriors"
        stored = env.get_doc("pc-projects", project_id)
        assert stored is not None
        assert stored["title"] == "Night exteriors"
    finally:
        env.delete_doc("pc-projects", project_id)


def test_rename_show_rejects_a_blank_title(env) -> None:
    body = open_show(env, title="Cafe pickup")
    project_id = str(body["project_id"])
    try:
        with pytest.raises(ValueError):
            rename_show(env, project_id, title="   ")
        stored = env.get_doc("pc-projects", project_id)
        assert stored is not None
        assert stored["title"] == "Cafe pickup"
    finally:
        env.delete_doc("pc-projects", project_id)
