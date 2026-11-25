#!/usr/bin/env python3
"""Apply the Graph/Telegram 13.2 SettingsActivity runtime-mapping correction."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
source = root / "app/src/main/java/com/my/televip/obfuscate/auto/AutoMappingResolver.java"
if not source.is_file():
    raise SystemExit(f"AutoMappingResolver.java not found under {root}")
text = source.read_text(encoding="utf-8")
text = text.replace("private static final int SCHEMA_VERSION = 32;", "private static final int SCHEMA_VERSION = 33;")

start_marker = "    private void resolveSettingsClasses(DexScanner scanner) {"
end_marker = "\n    private static String findTheme("
if start_marker not in text or end_marker not in text:
    raise SystemExit("Unexpected AutoMappingResolver layout; refusing to patch an unknown source revision")
start = text.index(start_marker)
end = text.index(end_marker, start)

new_method = r"""    private void resolveSettingsClasses(DexScanner scanner) {
        final String[] uItemDescHolder = new String[1];
        final String[] factoryOfName = new String[1];
        final String[][] factoryOfParams = new String[1][];
        final String[] factoryBindName = new String[1];
        final String[] fillItemsName = new String[1];
        final String[] onClickName = new String[1];
        final String[] settingsDescHolder = new String[1];

        // Telegram 13.2 moved SettingsActivity to instance callbacks:
        // fillItems(ArrayList, UniversalAdapter) and onClick(UItem, View, int, float, float).
        // Older clients used static callbacks. Match the real SettingCell.Factory by verifying
        // that the resolved SettingsActivity.fillItems method invokes that factory's of(...).
        String factoryDesc = scanner.findClassByPredicate("Lorg/telegram/ui/", (desc, fields, methods) -> {
            if (desc.startsWith("Lorg/telegram/ui/Components/")) return false;

            for (DexScanner.MethodInfo of : methods) {
                String candidateUItem = of.returnDesc;
                String[] ofParams = of.paramDescs;
                if (!of.isStatic || !candidateUItem.startsWith("Lorg/telegram/ui/Components/")
                        || (ofParams.length != 6 && ofParams.length != 7)
                        || !"I".equals(ofParams[0]) || !"I".equals(ofParams[1])
                        || !"I".equals(ofParams[2]) || !"I".equals(ofParams[3])
                        || !"Ljava/lang/CharSequence;".equals(ofParams[4])
                        || !"Ljava/lang/CharSequence;".equals(ofParams[5])) {
                    continue;
                }

                String bindName = null;
                for (DexScanner.MethodInfo bind : methods) {
                    if (!bind.isStatic && "V".equals(bind.returnDesc) && bind.paramDescs.length >= 3
                            && "Landroid/view/View;".equals(bind.paramDescs[0])
                            && candidateUItem.equals(bind.paramDescs[1]) && "Z".equals(bind.paramDescs[2])) {
                        bindName = bind.name;
                        break;
                    }
                }
                if (bindName == null) continue;

                final String candidateFactory = desc;
                final String candidateOfName = of.name;
                final String[] candidateOfParams = ofParams;
                final String itemDesc = candidateUItem;
                final String candidateBind = bindName;

                String resolvedSettingsActivity = scanner.findClassByPredicate("Lorg/telegram/ui/", (candidateSettings, fs, ms) -> {
                    if (candidateSettings.contains("$")
                            || candidateSettings.startsWith("Lorg/telegram/ui/Components/")
                            || candidateSettings.startsWith("Lorg/telegram/ui/Cells/")) return false;

                    DexScanner.MethodInfo fill = null;
                    DexScanner.MethodInfo click = null;
                    for (DexScanner.MethodInfo m : ms) {
                        if (!"V".equals(m.returnDesc)) continue;
                        String[] mp = m.paramDescs;

                        // Modern, non-static UniversalRecyclerView callbacks.
                        if (!m.isStatic && mp.length == 2 && "Ljava/util/ArrayList;".equals(mp[0])
                                && mp[1].startsWith("Lorg/telegram/ui/Components/")) {
                            fill = m;
                        }
                        if (!m.isStatic && mp.length == 5 && itemDesc.equals(mp[0])
                                && "Landroid/view/View;".equals(mp[1]) && "I".equals(mp[2])
                                && "F".equals(mp[3]) && "F".equals(mp[4])) {
                            click = m;
                        }

                        // Legacy static callback signatures, retained for older Telegram clients.
                        if (m.isStatic && mp.length == 2 && candidateSettings.equals(mp[0])
                                && "Ljava/util/ArrayList;".equals(mp[1])) fill = m;
                        if (m.isStatic && mp.length == 2 && candidateSettings.equals(mp[0])
                                && itemDesc.equals(mp[1])) click = m;
                    }
                    if (fill == null || click == null) return false;

                    boolean callsThisFactory = false;
                    for (DexScanner.MethodRef ref : scanner.getCalledMethodsInMethod(
                            candidateSettings, fill.name, fill.paramDescs, candidateFactory)) {
                        if (candidateOfName.equals(ref.name) && itemDesc.equals(ref.returnDesc)
                                && java.util.Arrays.equals(candidateOfParams, ref.paramDescs)) {
                            callsThisFactory = true;
                            break;
                        }
                    }
                    if (!callsThisFactory) return false;

                    settingsDescHolder[0] = candidateSettings;
                    fillItemsName[0] = fill.name;
                    onClickName[0] = click.name;
                    return true;
                });

                if (resolvedSettingsActivity != null) {
                    uItemDescHolder[0] = itemDesc;
                    factoryOfName[0] = candidateOfName;
                    factoryOfParams[0] = candidateOfParams;
                    factoryBindName[0] = candidateBind;
                    return true;
                }
            }
            return false;
        });

        if (factoryDesc == null || uItemDescHolder[0] == null || settingsDescHolder[0] == null) {
            Logger.w("AutoMappingResolver: could not resolve the Telegram 13.2 SettingsActivity/SettingCell.Factory pattern");
            return;
        }

        String itemDesc = uItemDescHolder[0];
        addClass("org.telegram.ui.SettingsActivity$SettingCell$Factory", factoryDesc);
        addMethod("SettingsActivity$SettingCell$Factory", "of", factoryOfName[0]);
        addMethod("SettingsActivity$SettingCell$Factory", "bindView", factoryBindName[0]);
        addClass(ClassNames.UITEM, itemDesc);

        // Resolve UItem fields from the selected SettingCell.Factory.of() implementation.
        String firstInt = null;
        String textField = null;
        String subtextField = null;
        for (DexScanner.FieldInfo f : scanner.getWrittenFieldsInMethod(
                factoryDesc, factoryOfName[0], factoryOfParams[0], itemDesc)) {
            if ("I".equals(f.typeDesc) && firstInt == null) {
                firstInt = f.name;
            } else if ("Ljava/lang/CharSequence;".equals(f.typeDesc)) {
                if (textField == null) textField = f.name;
                else if (subtextField == null && !f.name.equals(textField)) subtextField = f.name;
            }
        }
        if (firstInt != null) addField("UItem", "id", firstInt);
        if (textField != null) addField("UItem", "text", textField);
        if (subtextField != null) addField("UItem", "subtext", subtextField);

        addClass("org.telegram.ui.SettingsActivity", settingsDescHolder[0]);
        addMethod("SettingsActivity", "fillItems", fillItemsName[0]);
        addMethod("SettingsActivity", "onClick", onClickName[0]);
        Logger.w("AutoMappingResolver: mapped Telegram 13.2 SettingsActivity=" + settingsDescHolder[0]
                + ", SettingCell.Factory=" + factoryDesc + ", UItem=" + itemDesc);
    }
"""

text = text[:start] + new_method + text[end:]
source.write_text(text, encoding="utf-8")

hook = root / "app/src/main/java/com/my/televip/settings/hook/SettingsHook.java"
hs = hook.read_text(encoding="utf-8")
old_loop = """                                for (int i = 0; i < arrayList.size(); i++) {
                                    UItem item = new UItem(arrayList.get(i));

                                    if (item.getText() != null && item.getSubtext() != null) {
                                        arrayList.add(i, uItem);
                                        break;
                                    }
                                }
"""
new_loop = """                                int accountRowIndex = -1;
                                int fallbackIndex = -1;
                                for (int i = 0; i < arrayList.size(); i++) {
                                    try {
                                        UItem item = new UItem(arrayList.get(i));
                                        int itemId = item.getID();
                                        // Telegram 13.2 uses SettingCell id=1 for Account.
                                        // Keep Graph's own account-management rows above Re: TeleVIP.
                                        if (itemId == 1) {
                                            accountRowIndex = i;
                                            break;
                                        }
                                        if (fallbackIndex < 0 && item.getText() != null && item.getSubtext() != null) {
                                            fallbackIndex = i;
                                        }
                                    } catch (Throwable ignored) { }
                                }
                                int insertIndex = accountRowIndex >= 0 ? accountRowIndex : fallbackIndex;
                                if (insertIndex >= 0) {
                                    arrayList.add(insertIndex, uItem);
                                    Logger.w("SettingsHook: inserted Re: TeleVIP row at index " + insertIndex);
                                } else {
                                    Logger.w("SettingsHook: could not find Account row; Re: TeleVIP was not inserted");
                                }
"""
if old_loop in hs:
    hs = hs.replace(old_loop, new_loop)
elif "if (itemId == 1)" not in hs:
    raise SystemExit("SettingsHook insertion loop has an unexpected source shape")

if "SettingsHook: SettingsCell.Factory/of mapping is missing" not in hs:
    key = '            final String ofName = Obfuscate.getMethodName("SettingsActivity$SettingCell$Factory", "of");\n'
    if key not in hs:
        raise SystemExit("SettingsHook factory mapping declaration not found")
    hs = hs.replace(key, key + """            if (SettingsActivity$SettingCell$FactoryClass == null || ofName == null) {
                Logger.w("SettingsHook: SettingsCell.Factory/of mapping is missing; cannot add Re: TeleVIP");
                return;
            }
""")

if "new UItem(existing).getID() == 8353847" not in hs:
    key = "                            if (arrayList != null) {\n"
    if key not in hs:
        raise SystemExit("SettingsHook ArrayList block not found")
    hs = hs.replace(key, key + """                                for (Object existing : arrayList) {
                                    if (existing != null) {
                                        try {
                                            if (new UItem(existing).getID() == 8353847) return;
                                        } catch (Throwable ignored) { }
                                    }
                                }
""", 1)
hook.write_text(hs, encoding="utf-8")

manager = root / "app/src/main/java/com/my/televip/settings/SettingsManager.java"
ms = manager.read_text(encoding="utf-8")
init_line = "        SettingsActivity.init(settingsController);\n"
old_resolver_block = """        // Telegraph ships a partial static mapping. Discover the obfuscated SettingsActivity
        // and SettingCell.Factory at runtime before deciding whether to use the legacy drawer.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            ObfuscationManager.ensureRuntimeSettingsMappings();
        }

"""
new_resolver_block = """        // Resolve the Graph/Telegram 13.2 UI callbacks before installing any hooks.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            ObfuscationManager.ensureRuntimeSettingsMappings();
        }

"""
if init_line not in ms:
    raise SystemExit("SettingsManager SettingsActivity.init call not found")
if old_resolver_block in ms:
    ms = ms.replace(old_resolver_block, "", 1)
if new_resolver_block not in ms:
    ms = ms.replace(init_line, new_resolver_block + init_line, 1)

old_fallback = """        } else {
            settings.oldSettings(settingsController);
        }
"""
new_fallback = """        } else if (ClientManager.is(ClientManager.Client.Telegraph)) {
            com.my.televip.logging.Logger.w("SettingsManager: Telegraph SettingsActivity/Factory mapping missing; modern Settings tab was not hooked. Activity="
                    + SettingsActivityClass + ", Factory=" + SettingsActivity$SettingCell$FactoryClass);
        } else {
            settings.oldSettings(settingsController);
        }
"""
if "modern Settings tab was not hooked" not in ms and old_fallback in ms:
    ms = ms.replace(old_fallback, new_fallback, 1)
manager.write_text(ms, encoding="utf-8")

if "SCHEMA_VERSION = 33" not in text:
    raise SystemExit("Runtime mapping cache schema was not bumped")
print("Applied Graph/Telegram 13.2 SettingsActivity mapping, row placement, duplicate guard, and cache-version fixes")
