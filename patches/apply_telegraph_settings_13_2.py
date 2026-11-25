#!/usr/bin/env python3
"""Resolve Graph 13.2 Settings hooks from the actual fillItems call graph."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
resolver = root / "app/src/main/java/com/my/televip/obfuscate/auto/AutoMappingResolver.java"
if not resolver.is_file():
    raise SystemExit(f"Missing resolver: {resolver}")
s = resolver.read_text(encoding="utf-8")

start = "    private void resolveSettingsClasses(DexScanner scanner) {"
end = "\n    private static String findTheme("
if start not in s or end not in s:
    raise SystemExit("AutoMappingResolver source layout mismatch; no changes made")
a, b = s.index(start), s.index(end, s.index(start))

method = r"""    private void resolveSettingsClasses(DexScanner scanner) {
        // Graph Messenger 13.2.2.2 keeps SettingsActivity in its original package/name.
        // Its Telegraph.json profile already identifies fillItems=r0 and onClick=v0,
        // but does not contain the nested SettingCell.Factory mapping. Resolve that
        // missing class by following the actual calls made by SettingsActivity.fillItems.
        final String settingsDesc = "Lorg/telegram/ui/SettingsActivity;";
        List<DexScanner.MethodInfo> settingsMethods = scanner.getMethods(settingsDesc);
        if (settingsMethods.isEmpty()) {
            Logger.w("AutoMappingResolver: Graph SettingsActivity class not present under the Telegram name");
            return;
        }

        DexScanner.MethodInfo fillMethod = null;
        DexScanner.MethodRef factoryOf = null;
        for (DexScanner.MethodInfo candidate : settingsMethods) {
            if (!"V".equals(candidate.returnDesc)) continue;
            boolean takesArrayList = false;
            for (String p : candidate.paramDescs) {
                if ("Ljava/util/ArrayList;".equals(p)) {
                    takesArrayList = true;
                    break;
                }
            }
            if (!takesArrayList || candidate.codeOff == 0) continue;

            List<DexScanner.MethodRef> calls = scanner.getCalledMethodsInMethod(
                    settingsDesc, candidate.name, candidate.paramDescs, null);
            for (DexScanner.MethodRef call : calls) {
                String[] p = call.paramDescs;
                if (call.ownerDesc == null || !call.ownerDesc.startsWith("Lorg/telegram/ui/")
                        || !call.returnDesc.startsWith("Lorg/telegram/ui/Components/")
                        || (p.length != 6 && p.length != 7)
                        || !"I".equals(p[0]) || !"I".equals(p[1])
                        || !"I".equals(p[2]) || !"I".equals(p[3])
                        || !"Ljava/lang/CharSequence;".equals(p[4])
                        || !"Ljava/lang/CharSequence;".equals(p[5])) {
                    continue;
                }
                fillMethod = candidate;
                factoryOf = call;
                break;
            }
            if (factoryOf != null) break;
        }

        if (fillMethod == null || factoryOf == null) {
            Logger.w("AutoMappingResolver: Graph SettingsActivity.fillItems call graph did not expose SettingCell.Factory.of");
            return;
        }

        final String factoryDesc = factoryOf.ownerDesc;
        final String uItemDesc = factoryOf.returnDesc;
        addClass("org.telegram.ui.SettingsActivity", settingsDesc);
        addClass("org.telegram.ui.SettingsActivity$SettingCell$Factory", factoryDesc);
        addClass(ClassNames.UITEM, uItemDesc);
        addMethod("SettingsActivity", "fillItems", fillMethod.name);
        addMethod("SettingsActivity$SettingCell$Factory", "of", factoryOf.name);

        // Resolve the exact view binder on the factory class, using its real UItem parameter.
        String bindName = null;
        for (DexScanner.MethodInfo m : scanner.getMethods(factoryDesc)) {
            if (!m.isStatic && "V".equals(m.returnDesc) && m.paramDescs.length >= 3
                    && "Landroid/view/View;".equals(m.paramDescs[0])
                    && uItemDesc.equals(m.paramDescs[1]) && "Z".equals(m.paramDescs[2])) {
                bindName = m.name;
                break;
            }
        }
        if (bindName != null) {
            addMethod("SettingsActivity$SettingCell$Factory", "bindView", bindName);
        }

        // Resolve UItem's fields from writes performed by this exact Factory.of overload.
        String idField = null;
        String textField = null;
        String subtextField = null;
        for (DexScanner.FieldInfo f : scanner.getWrittenFieldsInMethod(
                factoryDesc, factoryOf.name, factoryOf.paramDescs, uItemDesc)) {
            if ("I".equals(f.typeDesc) && idField == null) {
                idField = f.name;
            } else if ("Ljava/lang/CharSequence;".equals(f.typeDesc)) {
                if (textField == null) textField = f.name;
                else if (subtextField == null && !f.name.equals(textField)) subtextField = f.name;
            }
        }
        if (idField != null) addField("UItem", "id", idField);
        if (textField != null) addField("UItem", "text", textField);
        if (subtextField != null) addField("UItem", "subtext", subtextField);

        // Graph's profile names this callback v0. Confirm it accepts the discovered UItem;
        // use the structural match first so this also survives a Graph rebuild/renaming.
        String clickName = null;
        for (DexScanner.MethodInfo m : settingsMethods) {
            if (!"V".equals(m.returnDesc)) continue;
            for (String p : m.paramDescs) {
                if (uItemDesc.equals(p)) {
                    clickName = m.name;
                    break;
                }
            }
            if (clickName != null) break;
        }
        if (clickName == null) {
            for (DexScanner.MethodInfo m : settingsMethods) {
                if ("v0".equals(m.name) && "V".equals(m.returnDesc)) {
                    clickName = m.name;
                    break;
                }
            }
        }
        if (clickName != null) addMethod("SettingsActivity", "onClick", clickName);

        Logger.w("AutoMappingResolver: Graph settings hooks resolved from call graph: SettingsActivity="
                + settingsDesc + ", fillItems=" + fillMethod.name + ", Factory=" + factoryDesc
                + ", of=" + factoryOf.name + ", UItem=" + uItemDesc + ", bindView=" + bindName
                + ", onClick=" + clickName);
    }
"""
s = s[:a] + method + s[b:]
s = s.replace("private static final int SCHEMA_VERSION = 32;", "private static final int SCHEMA_VERSION = 34;")
resolver.write_text(s, encoding="utf-8")

manager = root / "app/src/main/java/com/my/televip/settings/SettingsManager.java"
ms = manager.read_text(encoding="utf-8")
if "ensureRuntimeSettingsMappings();" not in ms:
    marker = "        SettingsActivity.init(settingsController);\n"
    if marker not in ms:
        raise SystemExit("SettingsManager init marker not found")
    ms = ms.replace(marker, """        // Graph's static Telegraph profile has fillItems/onClick but omits SettingCell.Factory.
        // Resolve the missing factory from the APK call graph before deciding modern vs legacy UI.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            ObfuscationManager.ensureRuntimeSettingsMappings();
        }

""" + marker, 1)
manager.write_text(ms, encoding="utf-8")

# Make the hook fail loudly instead of silently choosing the legacy drawer when Graph's
# modern SettingsActivity exists but its factory mapping could not be resolved.
hook = root / "app/src/main/java/com/my/televip/settings/SettingsHook.java"
hs = hook.read_text(encoding="utf-8")
if "SettingsHook: modern Graph settings mapping incomplete" not in hs:
    needle = "    public void oldSettings(SettingsController settingsController){"
    diagnostic = """    public void graphSettingsMappingMissing() {
        Logger.w("SettingsHook: modern Graph settings mapping incomplete; not falling back to the legacy drawer");
    }

"""
    if needle in hs:
        hs = hs.replace(needle, diagnostic + needle, 1)
hook.write_text(hs, encoding="utf-8")


# Ensure runtime mapping runs before any SettingsActivity hook/class lookup.
manager = root / "app/src/main/java/com/my/televip/settings/SettingsManager.java"
ms = manager.read_text(encoding="utf-8")
init_marker = "        SettingsActivity.init(settingsController);\\n"
resolver_call = """        // Graph's static profile omits the nested Factory class; resolve it from fillItems bytecode first.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            ObfuscationManager.ensureRuntimeSettingsMappings();
        }

"""
if init_marker not in ms:
    raise SystemExit("SettingsManager init marker not found")
if resolver_call not in ms:
    ms = ms.replace(init_marker, resolver_call + init_marker, 1)

old_branch = """        if (SettingsActivityClass != null && SettingsActivity$SettingCell$FactoryClass != null) {
            settings.newSettings(SettingsActivityClass, SettingsActivity$SettingCell$FactoryClass, settingsController);
        } else {
            settings.oldSettings(settingsController);
        }
"""
new_branch = """        if (SettingsActivityClass != null && SettingsActivity$SettingCell$FactoryClass != null) {
            Logger.w("SettingsManager: installing modern SettingsActivity hook; activity="
                    + SettingsActivityClass.getName() + ", factory="
                    + SettingsActivity$SettingCell$FactoryClass.getName());
            settings.newSettings(SettingsActivityClass, SettingsActivity$SettingCell$FactoryClass, settingsController);
        } else if (ClientManager.is(ClientManager.Client.Telegraph)) {
            Logger.w("SettingsManager: Graph modern settings hook not installed; activity="
                    + SettingsActivityClass + ", factory=" + SettingsActivity$SettingCell$FactoryClass
                    + ". Legacy drawer fallback intentionally disabled.");
        } else {
            settings.oldSettings(settingsController);
        }
"""
if old_branch not in ms:
    raise SystemExit("SettingsManager modern/legacy branch mismatch")
ms = ms.replace(old_branch, new_branch, 1)
manager.write_text(ms, encoding="utf-8")

print("Patched Graph SettingsActivity resolver to trace fillItems -> Factory.of -> UItem; cache schema=34")
