from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1]).resolve()
patch_dir = Path(__file__).resolve().parent

# Install the version-specific implementation derived from the supplied Graph APK.
hook_source = patch_dir / "TelegraphSettingsHook.java"
hook_target = root / "app/src/main/java/com/my/televip/settings/hook/TelegraphSettingsHook.java"
if not hook_source.is_file():
    raise SystemExit("Missing patches/TelegraphSettingsHook.java")
hook_target.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(hook_source, hook_target)

# Route Graph Messenger to TelegraphSettingsActivity and bypass the obsolete
# Telegram SettingsActivity/fillItems hook path for this client only.
manager = root / "app/src/main/java/com/my/televip/settings/SettingsManager.java"
text = manager.read_text(encoding="utf-8")
marker = "TelegraphSettingsHook().init"
if marker not in text:
    needle = "        SettingsActivity.init(settingsController);"
    if needle not in text:
        raise SystemExit("Could not find SettingsActivity.init insertion point")
    addition = needle + """

        // Graph 13.2.2.2: hook its actual TelegraphSettingsActivity RecyclerView.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            new com.my.televip.settings.hook.TelegraphSettingsHook()
                    .init(Utils.classLoader, settingsController);
            return;
        }"""
    text = text.replace(needle, addition, 1)
    manager.write_text(text, encoding="utf-8")

# ConcatAdapter is used to append the Re: TeleVIP row without replacing Graph's
# existing settings adapter or relying on Telegram's older UItem factory.
gradle = root / "app/build.gradle"
build_text = gradle.read_text(encoding="utf-8")
dependency = '    implementation("androidx.recyclerview:recyclerview:1.4.0")'
if "androidx.recyclerview:recyclerview" not in build_text:
    needle = "    implementation(libs.appcompat)"
    if needle not in build_text:
        raise SystemExit("Could not find appcompat dependency insertion point")
    build_text = build_text.replace(needle, needle + "\n" + dependency, 1)
    gradle.write_text(build_text, encoding="utf-8")

print("Installed Graph Messenger 13.2.2.2 TelegraphSettingsActivity hook")
