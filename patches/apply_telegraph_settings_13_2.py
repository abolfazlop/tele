#!/usr/bin/env python3
"""Patch TeleVipNext to resolve Telegraph Settings hooks by bytecode behaviour."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()

# Keep the original behaviour-based DexScanner resolver. The previous patch replaced
# it with a hard-coded SettingsActivity descriptor, which cannot discover renamed classes.
resolver = root / "app/src/main/java/com/my/televip/obfuscate/auto/AutoMappingResolver.java"
rs = resolver.read_text(encoding="utf-8")
start = "    private void resolveSettingsClasses(DexScanner scanner) {"
end = "\n    private static String findTheme("
if start not in rs or end not in rs:
    raise SystemExit("AutoMappingResolver.resolveSettingsClasses not found")
a = rs.index(start)
b = rs.index(end, a)

method = r"""    private void resolveSettingsClasses(DexScanner scanner) {
        final String[] uItemDescHolder = new String[1];
        final String[] factoryOfName = new String[1];
        final String[][] factoryOfParams = new String[1][];
        final String[] factoryBindName = new String[1];

        // Behaviour signature: a static factory taking four ints and two text values,
        // returning the client's UItem model. Do not depend on the obfuscated class name.
        String factoryDesc = scanner.findClassByPredicate("Lorg/telegram/ui/", (desc, fields, methods) -> {
            if (desc.contains("/Components/")) return false;
            for (DexScanner.MethodInfo m : methods) {
                if (m.isStatic && m.returnDesc.startsWith("Lorg/telegram/ui/Components/")
                        && (m.paramDescs.length == 6 || m.paramDescs.length == 7)
                        && "I".equals(m.paramDescs[0]) && "I".equals(m.paramDescs[1])
                        && "I".equals(m.paramDescs[2]) && "I".equals(m.paramDescs[3])
                        && "Ljava/lang/CharSequence;".equals(m.paramDescs[4])
                        && "Ljava/lang/CharSequence;".equals(m.paramDescs[5])) {
                    uItemDescHolder[0] = m.returnDesc;
                    factoryOfName[0] = m.name;
                    factoryOfParams[0] = m.paramDescs;
                    return true;
                }
            }
            return false;
        });

        if (factoryDesc == null || uItemDescHolder[0] == null) {
            Logger.w("AutoMappingResolver: Telegraph settings UItem factory behaviour not found");
            return;
        }
        String uItemDesc = uItemDescHolder[0];

        addClass("org.telegram.ui.SettingsActivity$SettingCell$Factory", factoryDesc);
        addMethod("SettingsActivity$SettingCell$Factory", "of", factoryOfName[0]);
        addClass(ClassNames.UITEM, uItemDesc);

        // Resolve Factory.bindView from its parameter types, not its obfuscated name.
        for (DexScanner.MethodInfo m : scanner.getMethods(factoryDesc)) {
            if (!m.isStatic && "V".equals(m.returnDesc) && m.paramDescs.length >= 3
                    && "Landroid/view/View;".equals(m.paramDescs[0])
                    && uItemDesc.equals(m.paramDescs[1]) && "Z".equals(m.paramDescs[2])) {
                factoryBindName[0] = m.name;
                break;
            }
        }
        if (factoryBindName[0] != null) {
            addMethod("SettingsActivity$SettingCell$Factory", "bindView", factoryBindName[0]);
        }

        // Read the UItem id/title/subtitle fields from writes in the discovered factory method.
        String firstInt = null;
        String cs1 = null, cs2 = null;
        for (DexScanner.FieldInfo f : scanner.getWrittenFieldsInMethod(
                factoryDesc, factoryOfName[0], factoryOfParams[0], uItemDesc)) {
            if ("I".equals(f.typeDesc) && firstInt == null) firstInt = f.name;
            else if ("Ljava/lang/CharSequence;".equals(f.typeDesc)) {
                if (cs1 == null) cs1 = f.name;
                else if (cs2 == null && !f.name.equals(cs1)) cs2 = f.name;
            }
        }
        if (firstInt != null) addField("UItem", "id", firstInt);
        if (cs1 != null) addField("UItem", "text", cs1);
        if (cs2 != null) addField("UItem", "subtext", cs2);

        // Find the settings screen by behaviour. Accept both instance methods
        // (fillItems(ArrayList), onClick(UItem)) and static methods whose first
        // argument is the activity instance. This is the key compatibility fix.
        final String[] fillItemsName = new String[1];
        final String[] onClickName = new String[1];
        String settingsDesc = scanner.findClassByPredicate("Lorg/telegram/ui/", (desc, fields, methods) -> {
            if (desc.contains("$") || desc.contains("/Components/") || desc.contains("/Cells/")) return false;
            String fill = null, click = null;
            for (DexScanner.MethodInfo m : methods) {
                if (!"V".equals(m.returnDesc) || m.name.startsWith("<")) continue;
                boolean hasArrayList = false;
                boolean hasUItem = false;
                for (String p : m.paramDescs) {
                    if ("Ljava/util/ArrayList;".equals(p)) hasArrayList = true;
                    if (uItemDesc.equals(p)) hasUItem = true;
                }
                if (hasArrayList) fill = m.name;
                if (hasUItem) click = m.name;
            }
            if (fill != null && click != null && !fill.equals(click)) {
                fillItemsName[0] = fill;
                onClickName[0] = click;
                return true;
            }
            return false;
        });

        if (settingsDesc != null) {
            addClass("org.telegram.ui.SettingsActivity", settingsDesc);
            addMethod("SettingsActivity", "fillItems", fillItemsName[0]);
            addMethod("SettingsActivity", "onClick", onClickName[0]);
            Logger.w("AutoMappingResolver: Telegraph Settings hooks found by behaviour: "
                    + settingsDesc + " fillItems=" + fillItemsName[0] + " onClick=" + onClickName[0]
                    + " Factory=" + factoryDesc + " UItem=" + uItemDesc);
        } else {
            Logger.w("AutoMappingResolver: UItem factory found, but settings screen behaviour was not found");
        }
    }
"""
rs = rs[:a] + method + rs[b:]
rs = rs.replace("private static final int SCHEMA_VERSION = 32;", "private static final int SCHEMA_VERSION = 35;")
resolver.write_text(rs, encoding="utf-8")

# Ensure mappings are resolved before SettingsActivity hooks and before class lookup.
manager = root / "app/src/main/java/com/my/televip/settings/SettingsManager.java"
ms = manager.read_text(encoding="utf-8")
if "import com.my.televip.logging.Logger;" not in ms:
    ms = ms.replace("import com.my.televip.obfuscate.ObfuscationManager;",
                    "import com.my.televip.obfuscate.ObfuscationManager;\nimport com.my.televip.logging.Logger;")
block = """        // Telegraph ships a partial static mapping. Discover the obfuscated SettingsActivity
        // and SettingCell.Factory at runtime before deciding whether to use the legacy drawer.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            ObfuscationManager.ensureRuntimeSettingsMappings();
        }

"""
ms = ms.replace(block, "")
marker = "        SettingsActivity.init(settingsController);"
call = """        // Resolve Graph/Telegraph's renamed settings classes before any settings hook lookup.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            ObfuscationManager.ensureRuntimeSettingsMappings();
        }

"""
if marker not in ms:
    raise SystemExit("SettingsManager.init marker not found")
if call not in ms:
    ms = ms.replace(marker, call + marker, 1)

old_branch = """        if (SettingsActivityClass != null && SettingsActivity$SettingCell$FactoryClass != null) {
            settings.newSettings(SettingsActivityClass, SettingsActivity$SettingCell$FactoryClass, settingsController);
        } else {
            settings.oldSettings(settingsController);
        }
"""
new_branch = """        if (SettingsActivityClass != null && SettingsActivity$SettingCell$FactoryClass != null) {
            Logger.w("SettingsManager: installing modern settings hook for "
                    + SettingsActivityClass.getName() + " / "
                    + SettingsActivity$SettingCell$FactoryClass.getName());
            settings.newSettings(SettingsActivityClass, SettingsActivity$SettingCell$FactoryClass, settingsController);
        } else if (ClientManager.is(ClientManager.Client.Telegraph)) {
            Logger.w("SettingsManager: Telegraph modern settings hook NOT installed. activity="
                    + SettingsActivityClass + " factory=" + SettingsActivity$SettingCell$FactoryClass);
        } else {
            settings.oldSettings(settingsController);
        }
"""
if old_branch not in ms:
    raise SystemExit("SettingsManager modern/legacy branch not found")
ms = ms.replace(old_branch, new_branch, 1)
manager.write_text(ms, encoding="utf-8")

# Handle every primitive type for an optional seventh Factory.of argument.
hook = root / "app/src/main/java/com/my/televip/settings/hook/SettingsHook.java"
hs = hook.read_text(encoding="utf-8")
old_arg = """                                                Object arg6 = pt[6] == boolean.class ? Boolean.FALSE
                                                        : (pt[6] == int.class ? Integer.valueOf(0) : null);
"""
new_arg = """                                                Object arg6 = null;
                                                if (pt[6].isPrimitive()) {
                                                    if (pt[6] == boolean.class) arg6 = Boolean.FALSE;
                                                    else if (pt[6] == char.class) arg6 = Character.valueOf((char) 0);
                                                    else if (pt[6] == byte.class) arg6 = Byte.valueOf((byte) 0);
                                                    else if (pt[6] == short.class) arg6 = Short.valueOf((short) 0);
                                                    else if (pt[6] == int.class) arg6 = Integer.valueOf(0);
                                                    else if (pt[6] == long.class) arg6 = Long.valueOf(0L);
                                                    else if (pt[6] == float.class) arg6 = Float.valueOf(0f);
                                                    else if (pt[6] == double.class) arg6 = Double.valueOf(0d);
                                                }
"""
if old_arg in hs:
    hs = hs.replace(old_arg, new_arg, 1)
hook.write_text(hs, encoding="utf-8")

print("Patched Telegraph settings hooks using behaviour-based DexScanner resolution (schema 35)")
