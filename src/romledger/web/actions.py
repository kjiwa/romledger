from fastapi import HTTPException

from romledger import importer, scan
from romledger.config import ConfigError
from romledger.context import Context
from romledger.web.deps import Services
from romledger.web.jobs import JobBusy, Running, Work


def start_scan(context: Context, services: Services) -> Running:
    slugs = _slugs(context)

    def work() -> bool:
        scan.scan_each(
            slugs,
            lambda slug: scan.scan_platform(
                context.config, slug, context.data_dir, services.tools.igir_report
            ),
        )
        return True

    return _start("scan", services, work)


def start_import(context: Context, services: Services) -> Running:
    _slugs(context)
    tools = services.tools

    def work() -> bool:
        result = importer.import_inboxes(
            context.config,
            context.data_dir,
            False,
            tools.igir_report,
            tools.igir_move,
            tools.hook,
        )
        return importer.print_result(result, dry_run=False) == 0

    return _start("import", services, work)


def _slugs(context: Context) -> list[str]:
    slugs = list(context.config.platforms)
    if not slugs:
        raise HTTPException(400, importer.NO_PLATFORMS)
    try:
        scan.require_dats(context.config, slugs, context.data_dir)
    except ConfigError as error:
        raise HTTPException(400, str(error)) from error
    return slugs


def _start(kind: str, services: Services, work: Work) -> Running:
    try:
        return services.jobs.start(kind, work)
    except JobBusy as error:
        raise HTTPException(409, str(error)) from error
