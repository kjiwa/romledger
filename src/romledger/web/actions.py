from fastapi import HTTPException

from romledger import importer, scan
from romledger.context import Context
from romledger.web.deps import Services
from romledger.web.jobs import JobBusy, Running, Work


def start_scan(context: Context, services: Services) -> Running:
    def work() -> bool:
        slugs = scan.ensure_dats(context.config, list(context.config.platforms), context.data_dir)
        scan.scan_platforms(context.config, slugs, context.data_dir, services.tools.igir_report)
        print(f"scanned {len(slugs)} platform(s)")
        return True

    return _start("scan", services, work)


def start_import(context: Context, services: Services) -> Running:
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


def _start(kind: str, services: Services, work: Work) -> Running:
    try:
        return services.jobs.start(kind, work)
    except JobBusy as error:
        raise HTTPException(409, str(error)) from error
