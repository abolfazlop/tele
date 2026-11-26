#!/usr/bin/env python3
"""Apply Graph Messenger 13.2.2.2 ProfileActivity/ai1 row injection."""
from pathlib import Path
import re
import shutil
import sys

root = Path(sys.argv[1]).resolve()
patch_dir = Path(__file__).resolve().parent

hook_source = patch_dir / "GraphProfileSettingsHook.java"
hook_target = root / "app/src/main/java/com/my/televip/settings/hook/GraphProfileSettingsHook.java"
if not hook_source.is_file():
    raise SystemExit("Missing patches/GraphProfileSettingsHook.java")
hook_target.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(hook_source, hook_target)

manager = root / "app/src/main/java/com/my/televip/settings/SettingsManager.java"
text = manager.read_text(encoding="utf-8")

# Strip previous experimental Graph routing blocks. The ProfileActivity hook below is
# the only Telegraph path; Telegram and the other forks retain the standard settings hook.
text = re.sub(
    r"\s*//[^\n]*[Tt]elegraph[^\n]*\n\s*if \(ClientManager\.is\(ClientManager\.Client\.Telegraph\)\) \{\s*"
    r"ObfuscationManager\.ensureRuntimeSettingsMappings\(\);\s*\}\s*",
    "\n",
    text,
)
text = re.sub(
    r"\s*//[^\n]*Graph[^\n]*\n\s*if \(ClientManager\.is\(ClientManager\.Client\.Telegraph\)\) \{\s*"
    r"new com\.my\.televip\.settings\.hook\.TelegraphSettingsHook\(\).*?\n\s*return;\s*\}\s*",
    "\n",
    text,
    flags=re.S,
)

marker = "        SettingsActivity.init(settingsController);"
branch = """        // Graph Messenger 13.2.2.2 root Settings screen is ProfileActivity with adapter ai1.
        // Keep TeleVip's own settings/back-navigation initialization, then use Graph's row-index hook.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            new com.my.televip.settings.hook.GraphProfileSettingsHook(settingsController)
                    .install(Utils.classLoader);
            return;
        }

"""
if marker not in text:
    raise SystemExit("SettingsManager SettingsActivity.init() marker not found")
if "GraphProfileSettingsHook(settingsController)" not in text:
    text = text.replace(marker, marker + "\n\n" + branch, 1)
manager.write_text(text, encoding="utf-8")

gradle = root / "app/build.gradle"
build_text = gradle.read_text(encoding="utf-8")
dependency = '    implementation("androidx.recyclerview:recyclerview:1.4.0")'
if "androidx.recyclerview:recyclerview" not in build_text:
    marker = "    implementation(libs.appcompat)"
    if marker not in build_text:
        raise SystemExit("Could not find appcompat dependency insertion point")
    build_text = build_text.replace(marker, marker + "\n" + dependency, 1)
    gradle.write_text(build_text, encoding="utf-8")

# Build-time assertions: exact target screen and the Graph-only manager route.
assert "GraphProfileSettingsHook(settingsController)" in manager.read_text(encoding="utf-8")
hook = hook_target.read_text(encoding="utf-8")
for token in ("org.telegram.ui.ProfileActivity", "org.telegram.ui.ai1", "org.telegram.ui.yf1",
              "numberSectionRow", "getItemViewType", "onBindViewHolder"):
    if token not in hook:
        raise SystemExit("Graph hook missing expected target marker: " + token)
print("Applied Graph 13.2.2.2 ProfileActivity/ai1 row-index hook")
