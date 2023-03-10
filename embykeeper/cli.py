import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path

import click
import schedule
import toml
from dateutil import parser
from faker import Faker
from faker.providers import internet, profile
from loguru import logger
from rich.logging import Console, RichHandler

from .embywatcher import embywatcher
from .telechecker import telechecker
from .utils import CommandWithOptionalFlagValues, to_iterable


def _formatter(record):
    extra = record["extra"]
    scheme = extra.get("scheme", None)

    def ifextra(keys, pattern="{}"):
        keys = to_iterable(keys)
        if all(k in extra for k in keys):
            return pattern.format(*[f"{{extra[{k}]}}" for k in keys])
        else:
            return ""

    if scheme == "telechecker":
        username = ifextra("username", " ([cyan]{}[/])")
        name = ifextra("name", "([magenta]{}[/]) ")
        return f"[blue]Telechecker[/]{username}: {name}{{message}}"
    elif scheme == "embywatcher":
        ident = ifextra(["server", "username"], " ([cyan]{}:{}[/])")
        return f"[blue]Embywatcher[/]{ident}: {{message}}"
    else:
        return "{message}"


logger.remove()
logger.add(RichHandler(console=Console(stderr=True), markup=True), format=_formatter)


def _get_faked_config():
    fake = Faker()
    fake.add_provider(internet)
    fake.add_provider(profile)
    account = {}
    account["timeout"] = 240
    account["retries"] = 10
    account["proxy"] = {
        "host": "127.0.0.1",
        "port": "1080",
        "scheme": "socks5",
    }
    account["telegram"] = []
    for _ in range(2):
        account["telegram"].append(
            {
                "api_id": fake.numerify(text="########"),
                "api_hash": uuid.uuid4().hex,
                "phone": f'+861{fake.numerify(text="##########")}',
            }
        )
    account["emby"] = []
    for _ in range(2):
        account["emby"].append(
            {
                "url": fake.url(["https"]),
                "username": fake.profile()["username"],
                "password": fake.password(),
            }
        )
    return account


@click.command(cls=CommandWithOptionalFlagValues)
@click.argument("config", required=False, type=click.Path(dir_okay=False, exists=True))
@click.option(
    "--telegram",
    "-t",
    type=str,
    flag_value="08:00",
    help="????????????????????????Telegram bot??????",
)
@click.option(
    "--telegram-follow", is_flag=True, hidden=True, help="??????Telegram?????????????????????ChatID"
)
@click.option("--emby", "-e", type=int, flag_value=7, help="????????????????????????Emby??????")
@click.option("--instant/--no-instant", default=True, help="??????????????????????????????")
@click.option("--quiet/--no-quiet", default=False, help="????????????????????????????????????, ?????????????????????????????????")
def cli(config, telegram, telegram_follow, emby, instant, quiet):
    if not config:
        logger.warning("??????????????????toml?????????config??????.")
        default_config = "config.toml"
        if not Path(default_config).exists():
            with open(default_config, "w+") as f:
                toml.dump(_get_faked_config(), f)
                logger.warning(f'??????????????????????????????????????????"{default_config}"????????????')
        return
    with open(config) as f:
        config = toml.load(f)
    # TODO: add verification
    proxy = config.get("proxy", None)
    if proxy:
        proxy.setdefault("scheme", "socks5")
        proxy.setdefault("hostname", "127.0.0.1")
        proxy.setdefault("port", "1080")
    if quiet == True:
        config["quiet"] = True
    if telegram_follow:
        return asyncio.run(telechecker(config, follow=True))
    if not telegram and not emby:
        telegram = "08:00"
        emby = 7
    schedule_telegram = schedule.Scheduler()
    if telegram:
        telegram = parser.parse(telegram).time().strftime("%H:%M")
        schedule_telegram.every().day.at(telegram).do(lambda: asyncio.run(telechecker(config)))
    schedule_emby = schedule.Scheduler()
    if emby:
        schedule_emby.every(emby).days.at(datetime.now().strftime("%H:%M")).do(lambda: asyncio.run(embywatcher(config)))
    if instant:
        schedule_telegram.run_all()
        schedule_emby.run_all()
    if telegram:
        logger.info(f"?????????????????????{int(schedule_telegram.idle_seconds/3600)}???????????????.")
    if emby:
        logger.info(f"?????????????????????{int(schedule_emby.idle_seconds/3600/24)}????????????.")
    while True:
        schedule_telegram.run_pending()
        schedule_emby.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    cli()
