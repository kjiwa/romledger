from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from fastapi import Request

from romledger import igir, importer, scan, state
from romledger.context import Context
from romledger.web import auth
from romledger.web.jobs import Jobs

ContextFactory = Callable[[], Context]


@dataclass(frozen=True)
class Tools:
    igir_report: scan.IgirReport = igir.report
    igir_move: importer.IgirMove = igir.move
    hook: importer.RunHook = importer.run_hook


@dataclass(frozen=True)
class Services:
    context_factory: ContextFactory
    token: str
    tools: Tools = field(default_factory=Tools)
    jobs: Jobs = field(default_factory=Jobs)


def services(request: Request) -> Services:
    result: Services = request.app.state.services
    return result


def guard(request: Request) -> None:
    token = services(request).token
    if (
        request.method == "GET"
        and request.url.path == "/"
        and auth.matches(request.query_params.get("token"), token)
    ):
        return
    auth.authenticate(request, token)


def context(request: Request) -> Context:
    return services(request).context_factory()


def database(request: Request) -> Iterator[state.State]:
    with state.State(context(request).data_dir / "state.db") as opened:
        yield opened
