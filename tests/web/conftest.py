from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from romledger import igir
from romledger.web import app as web_app

from .support import TOKEN, Env, make_context


@pytest.fixture
def env(tmp_path: Path) -> Env:
    context = make_context(tmp_path)
    reports: list[str] = []
    moves: list[str] = []

    def report(
        dat_files: Sequence[Path],
        inputs: Sequence[Path],
        cache: Path,
        filters: igir.Filters | None = None,
        excludes: Sequence[str] = (),
    ) -> list[igir.ReportRow]:
        reports.append("report")
        return []

    def move(*args: object) -> None:
        moves.append("move")

    application = web_app.create_app(
        lambda: context, TOKEN, igir_report=report, igir_move=move, hook=lambda argv: 0
    )
    client = TestClient(application, headers={"Authorization": f"Bearer {TOKEN}"})
    return Env(
        context,
        context.config.library.inboxes[0],
        context.data_dir,
        client,
        reports,
        moves,
        application.state.services,
    )
