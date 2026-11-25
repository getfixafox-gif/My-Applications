"""Starter catalog: the entries offered on a brand-new installation.

This module is pure data — no database access. It is applied once by
:class:`app.services.starter_service.StarterService`.

Descriptions stay factual and short; every link was checked to exist. Icons are
*not* bundled: the application never reaches the network on its own, so the user
can fetch a favicon explicitly with the "Download icon" button.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Bumped when the starter list changes in a way that should re-run the import.
STARTER_VERSION = 1


@dataclass(frozen=True, slots=True)
class StarterLink:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class StarterEntry:
    title: str
    type: str
    category: str
    description: str
    links: tuple[StarterLink, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)


STARTER_ENTRIES: tuple[StarterEntry, ...] = (
    StarterEntry(
        title="Steam",
        type="Программа",
        category="Игры",
        description=(
            "Крупнейшая платформа цифровой дистрибуции игр: магазин, библиотека, "
            "мастерская модов и сообщество."
        ),
        links=(StarterLink("Магазин Steam", "https://store.steampowered.com/"),),
        tags=("игры", "магазин"),
    ),
    StarterEntry(
        title="Epic Games",
        type="Программа",
        category="Игры",
        description=(
            "Магазин и лаунчер Epic Games. Здесь же еженедельно раздают бесплатные игры."
        ),
        links=(StarterLink("Epic Games Store", "https://store.epicgames.com/"),),
        tags=("игры", "магазин"),
    ),
    StarterEntry(
        title="Battle.net",
        type="Программа",
        category="Игры",
        description=(
            "Лаунчер Blizzard: World of Warcraft, Overwatch, Diablo, StarCraft и Hearthstone."
        ),
        links=(StarterLink("Battle.net", "https://battle.net/"),),
        tags=("игры", "blizzard"),
    ),
    StarterEntry(
        title="OpenCode",
        type="Программа",
        category="Разработка",
        description=(
            "Терминальный ИИ-агент для разработки с открытым исходным кодом: "
            "работает в консоли и в редакторе."
        ),
        links=(StarterLink("opencode.ai", "https://opencode.ai/"),),
        tags=("разработка", "ии", "терминал"),
    ),
    StarterEntry(
        title="Firefox",
        type="Программа",
        category="Программы",
        description="Независимый браузер с открытым исходным кодом от Mozilla.",
        links=(StarterLink("Скачать Firefox", "https://www.mozilla.org/firefox/"),),
        tags=("браузер",),
    ),
    StarterEntry(
        title="Telegram",
        type="Программа",
        category="Программы",
        description=(
            "Мессенджер с облачными чатами, каналами, ботами и открытым API "
            "для десктопа и мобильных устройств."
        ),
        links=(StarterLink("telegram.org", "https://telegram.org/"),),
        tags=("мессенджер",),
    ),
    StarterEntry(
        title="Happ",
        type="Программа",
        category="Инструменты",
        description=(
            "Кроссплатформенное приложение для работы с прокси-серверами, "
            "построенное на ядре Xray."
        ),
        links=(StarterLink("happ.su", "https://happ.su/"),),
        tags=("прокси", "сеть"),
    ),
    StarterEntry(
        title="Zapret",
        type="Инструмент",
        category="Инструменты",
        description=(
            "Комплект скриптов zapret от Flowseal для обхода блокировок "
            "Discord и YouTube на Windows."
        ),
        links=(
            StarterLink(
                "GitHub: zapret-discord-youtube",
                "https://github.com/Flowseal/zapret-discord-youtube",
            ),
        ),
        tags=("сеть", "обход блокировок"),
    ),
    StarterEntry(
        title="TgWsProxy",
        type="Инструмент",
        category="Инструменты",
        description=(
            "Локальный MTProto-прокси сервер от Flowseal для частичного "
            "обхода блокировок Telegram."
        ),
        links=(
            StarterLink("GitHub: tg-ws-proxy", "https://github.com/Flowseal/tg-ws-proxy"),
        ),
        tags=("telegram", "прокси"),
    ),
)
