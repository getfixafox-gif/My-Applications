"""UI smoke tests (headless Qt)."""

from __future__ import annotations

import pytest

from app.services.entry_service import EntryDraft, LinkDraft
from app.ui.styles.theme import build_stylesheet, palette


@pytest.fixture()
def window(context, qapp):
    qapp.setStyleSheet(build_stylesheet("dark"))
    from app.ui.windows.main_window import MainWindow

    win = MainWindow(context)
    win.resize(1200, 780)
    win.show()
    qapp.processEvents()
    yield win
    win.save_window_state()
    win.close()
    qapp.processEvents()


def seed(context, count: int = 3) -> list:
    entries = []
    for index in range(count):
        entries.append(
            context.entries.create_entry(
                EntryDraft(
                    title=f"Entry {index}",
                    type="Программа" if index % 2 == 0 else "Сайт",
                    description=f"Description {index}",
                    links=[LinkDraft(f"Link {index}", f"https://example{index}.com")],
                )
            )
        )
    return entries


def test_themes_build() -> None:
    for theme in ("dark", "light"):
        sheet = build_stylesheet(theme)
        assert "QPushButton" in sheet
        assert palette(theme)["accent"].startswith("#")


def test_window_loads_entries(window, context) -> None:
    entries = seed(context, 3)
    window.reload_all()
    window.select_entry(entries[0].id)
    assert window.sidebar.list_widget.count() == 3
    assert window.detail.title_label.text() == "Entry 0"


def test_search_filters_list(window, context) -> None:
    seed(context, 3)
    window.reload_all()
    window.sidebar.search_edit.setText("Entry 2")
    window.reload_entries()
    assert window.sidebar.list_widget.count() == 1
    window.sidebar.search_edit.setText("nothing-matches")
    window.reload_entries()
    assert window.sidebar.list_widget.count() == 0
    assert window.sidebar.empty_label.isVisible()


def test_selecting_entry_updates_detail(window, context) -> None:
    entries = seed(context, 2)
    window.reload_all()
    window.select_entry(entries[1].id)
    assert window.detail.title_label.text() == "Entry 1"
    assert window.detail.links_layout.count() == 1
    assert window.detail.description_label.text() == "Description 1"


def test_empty_state_without_entries(window) -> None:
    window.reload_all()
    assert window.sidebar.list_widget.count() == 0
    assert window.detail.empty_widget.isVisible()


def test_category_filter(window, context) -> None:
    category = context.categories.create("Фильтр")
    context.entries.create_entry(EntryDraft(title="In cat", category_id=category.id))
    context.entries.create_entry(EntryDraft(title="Out of cat"))
    window.reload_all()
    index = window.sidebar.category_combo.findData(category.id)
    window.sidebar.category_combo.setCurrentIndex(index)
    window.reload_entries()
    assert window.sidebar.list_widget.count() == 1


def test_tag_filter(window, context) -> None:
    tag = context.tags.get_or_create("фильтр-тег")
    context.entries.create_entry(EntryDraft(title="Tagged", tag_ids=[tag.id]))
    context.entries.create_entry(EntryDraft(title="Plain"))
    window.reload_all()
    window.sidebar._toggle_tag(tag.id, True)
    window.reload_entries()
    assert window.sidebar.list_widget.count() == 1
    window.sidebar.clear_tag_filter()
    window.reload_entries()
    assert window.sidebar.list_widget.count() == 2


def test_theme_switch_updates_stylesheet(window, context, qapp) -> None:
    context.config.set("theme", "light")
    window.apply_theme()
    assert "background-color: #f4f6fa" in qapp.styleSheet()


def test_window_state_persisted(window, context) -> None:
    window.save_window_state()
    assert context.config.get("window_geometry")
    assert context.config.get("splitter_state")


def test_entry_dialog_draft(context, qapp) -> None:
    from app.ui.dialogs.entry_dialog import EntryDialog

    dialog = EntryDialog(theme="dark", context=context)
    dialog.title_edit.setText("  Draft title  ")
    dialog.type_edit.setText("Игра")
    dialog.description_edit.setPlainText("Text\nlines")
    draft = dialog.build_draft()
    assert draft.title.strip() == "Draft title"
    assert draft.type == "Игра"
    assert draft.description == "Text\nlines"
    assert draft.image_action == "keep"
    dialog.close()


def test_entry_dialog_edit_mode(context, qapp) -> None:
    from app.ui.dialogs.entry_dialog import EntryDialog

    entry = context.entries.create_entry(
        EntryDraft(
            title="Editable",
            description="desc",
            links=[LinkDraft("Site", "https://example.com")],
        )
    )
    dialog = EntryDialog(theme="dark", context=context, entry=entry)
    assert dialog.title_edit.text() == "Editable"
    assert len(dialog._links) == 1
    draft = dialog.build_draft()
    assert draft.links[0].id == entry.links[0].id
    dialog.close()


def test_tag_editor_creates_tags(context, qapp) -> None:
    from app.ui.widgets.tag_editor import TagEditor

    editor = TagEditor("dark")
    editor.set_resolver(lambda name: (context.tags.get_or_create(name).id, name))
    editor.input.setText("newtag")
    editor._commit_input()
    assert editor.tag_ids()
    assert context.tags.list_tags()[0].name == "newtag"


def test_settings_dialog_theme_switch(context, qapp) -> None:
    from app.ui.windows.settings_window import SettingsDialog

    dialog = SettingsDialog(context)
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("light"))
    assert context.config.get("theme") == "light"
    assert dialog.theme_changed
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
    dialog.close()


def test_settings_autobackup_toggle(context, qapp) -> None:
    from app.ui.windows.settings_window import SettingsDialog

    dialog = SettingsDialog(context)
    dialog.autobackup_check.setChecked(False)
    assert context.config.get("autobackup_enabled") is False
    dialog.autobackup_check.setChecked(True)
    dialog.keep_spin.setValue(7)
    assert context.config.get("autobackup_keep") == 7
    dialog.close()


def test_reference_dialog_crud(context, qapp) -> None:
    from app.ui.dialogs.reference_dialog import ReferenceDialog

    dialog = ReferenceDialog(context, theme="dark")
    initial = dialog.categories_widget.list_widget.count()
    assert dialog._create_category("UI категория")
    assert dialog.categories_widget.list_widget.count() == initial + 1
    assert not dialog._create_category("UI категория")  # duplicate rejected
    dialog.close()


def test_link_dialog_validation(qapp) -> None:
    from app.ui.dialogs.link_dialog import LinkDialog

    dialog = LinkDialog("dark")
    dialog.url_edit.setText("bad url with spaces")
    dialog._accept()
    assert dialog.result_link() is None
    assert dialog.error_label.isVisible() or dialog.error_label.text()

    dialog.url_edit.setText("example.com")
    dialog.title_edit.setText("Site")
    dialog._accept()
    link = dialog.result_link()
    assert link is not None and link.url == "https://example.com"
    dialog.close()


def test_open_url_is_not_automatic(window, monkeypatch) -> None:
    """Opening links must only happen on explicit user action."""
    calls = []
    monkeypatch.setattr(
        "app.ui.widgets.detail_panel.QDesktopServices.openUrl",
        lambda url: calls.append(url) or True,
    )
    seed(window.context, 1)
    window.reload_all()
    assert calls == []
    window.open_url("https://example.com")
    assert calls == ["https://example.com"]
