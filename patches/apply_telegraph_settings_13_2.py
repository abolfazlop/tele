from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

# 1) SettingsManager: use the real Graph SettingsActivity and Factory classes directly.
manager=root/'app/src/main/java/com/my/televip/settings/SettingsManager.java'
ms=manager.read_text(encoding='utf-8')
start=ms.index('    public static void init(SettingsController settingsController) {')
end=ms.index('\n    }\n\n}', start)+7
new_init='''    public static void init(SettingsController settingsController) {

        SettingsActivity.init(settingsController);

        Class<?> settingsActivityClass = XposedHelpers.findClassIfExists(
                Obfuscate.getClassName("org.telegram.ui.SettingsActivity"), Utils.classLoader);
        Class<?> factoryClass = XposedHelpers.findClassIfExists(
                Obfuscate.getClassName("org.telegram.ui.SettingsActivity$SettingCell$Factory"), Utils.classLoader);

        // Graph direct SettingsActivity fallback: do not depend on the failing runtime DEX heuristic.
        if (ClientManager.is(ClientManager.Client.Telegraph)) {
            if (settingsActivityClass == null) {
                settingsActivityClass = XposedHelpers.findClassIfExists(
                        "org.telegram.ui.SettingsActivity", Utils.classLoader);
            }
            if (factoryClass == null) {
                factoryClass = XposedHelpers.findClassIfExists(
                        "org.telegram.ui.SettingsActivity$SettingCell$Factory", Utils.classLoader);
            }
            if (factoryClass == null && settingsActivityClass != null) {
                for (Class<?> settingCell : settingsActivityClass.getDeclaredClasses()) {
                    if ("SettingCell".equals(settingCell.getSimpleName())) {
                        for (Class<?> nested : settingCell.getDeclaredClasses()) {
                            if ("Factory".equals(nested.getSimpleName())) {
                                factoryClass = nested;
                                break;
                            }
                        }
                    }
                }
            }
        }

        SettingsHook settings = new SettingsHook();
        if (settingsActivityClass != null && factoryClass != null) {
            com.my.televip.logging.Logger.w("SettingsManager: installing SettingsActivity hook: "
                    + settingsActivityClass.getName() + " / " + factoryClass.getName());
            settings.newSettings(settingsActivityClass, factoryClass, settingsController);
        } else if (ClientManager.is(ClientManager.Client.Telegraph)) {
            com.my.televip.logging.Logger.w("SettingsManager: Graph SettingsActivity/Factory class not found. activity="
                    + settingsActivityClass + ", factory=" + factoryClass);
        } else {
            settings.oldSettings(settingsController);
        }
        if (ClientManager.is(ClientManager.Client.ForkgramClassic)) settings.oldSettings(settingsController);
        if (ClientManager.is(ClientManager.Client.Turrit)) Turrit.showGhostModeDialog(settingsController);
    }
'''
ms=ms[:start]+new_init+ms[end:]
manager.write_text(ms,encoding='utf-8')

# 2) Hook the exact Re: TeleVIP integration surface independently:
# SettingsActivity.fillItems + SettingsActivity.onClick + SettingCell.Factory.of/bindView.
hook=root/'app/src/main/java/com/my/televip/settings/hook/SettingsHook.java'
hs=hook.read_text(encoding='utf-8')
start=hs.index('    public void newSettings(')
end=hs.index('    public void oldSettings(',start)
new_method=r'''    private static java.lang.reflect.Field findSemanticField(Class<?> type, String semantic) {
        String mapped = Obfuscate.getFieldName("UItem", semantic);
        for (Class<?> c = type; c != null; c = c.getSuperclass()) {
            if (mapped != null) {
                try {
                    java.lang.reflect.Field f = c.getDeclaredField(mapped);
                    f.setAccessible(true);
                    return f;
                } catch (Throwable ignored) { }
            }
            try {
                java.lang.reflect.Field f = c.getDeclaredField(semantic);
                f.setAccessible(true);
                return f;
            } catch (Throwable ignored) { }
        }
        return null;
    }

    private static Object readSemanticField(Object item, Class<?> itemClass, String semantic) {
        try {
            java.lang.reflect.Field f = findSemanticField(itemClass, semantic);
            return f != null ? f.get(item) : null;
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static int getItemId(Object item, Class<?> itemClass) {
        Object value = readSemanticField(item, itemClass, "id");
        return value instanceof Number ? ((Number) value).intValue() : Integer.MIN_VALUE;
    }

    private static boolean isTeleVipItem(Object item, Class<?> itemClass) {
        if (item == null || itemClass == null || !itemClass.isInstance(item)) return false;
        if (getItemId(item, itemClass) == 8353847) return true;
        Object text = readSemanticField(item, itemClass, "text");
        return text != null && "Re: TeleVIP".contentEquals(String.valueOf(text));
    }

    private static Method findFillItems(Class<?> activityClass) {
        Method fallback = null;
        String mappedMethod = Obfuscate.getMethodName("SettingsActivity", "fillItems");
        String mappedAdapter = Obfuscate.getClassName("org.telegram.ui.Components.UniversalAdapter");
        for (Method m : activityClass.getDeclaredMethods()) {
            if (m.getReturnType() != void.class) continue;
            boolean hasArrayList = false;
            boolean hasAdapter = false;
            for (Class<?> p : m.getParameterTypes()) {
                if (ArrayList.class.isAssignableFrom(p)) hasArrayList = true;
                if (p.getName().equals(mappedAdapter)
                        || p.getName().equals("org.telegram.ui.Components.UniversalAdapter")) hasAdapter = true;
            }
            if (!hasArrayList || !hasAdapter || java.lang.reflect.Modifier.isStatic(m.getModifiers())) continue;
            m.setAccessible(true);
            if (mappedMethod != null && mappedMethod.equals(m.getName())) return m;
            if ("fillItems".equals(m.getName())) return m;
            // The method name may be R8-renamed; the ArrayList + mapped UniversalAdapter signature is stable.
            if (fallback == null) fallback = m;
        }
        return fallback;
    }

    private static Method findOnClick(Class<?> activityClass, Class<?> itemClass) {
        Method fallback = null;
        String mapped = Obfuscate.getMethodName("SettingsActivity", "onClick");
        for (Method m : activityClass.getDeclaredMethods()) {
            if (m.getReturnType() != void.class) continue;
            Class<?>[] p = m.getParameterTypes();
            boolean hasItem = false, hasView = false, hasInt = false;
            int floatCount = 0;
            for (Class<?> t : p) {
                if (itemClass.isAssignableFrom(t)) hasItem = true;
                if (View.class.isAssignableFrom(t)) hasView = true;
                if (t == int.class) hasInt = true;
                if (t == float.class) floatCount++;
            }
            if (!hasItem || !hasView) continue;
            m.setAccessible(true);
            if (mapped != null && mapped.equals(m.getName())) return m;
            if ("onClick".equals(m.getName())) return m;
            if (hasInt && floatCount >= 2) fallback = m;
        }
        return fallback;
    }

    private static Method findFactoryOf(Class<?> factoryClass, Class<?> itemClass) {
        Method best = null;
        for (Method m : factoryClass.getDeclaredMethods()) {
            if (!java.lang.reflect.Modifier.isStatic(m.getModifiers())) continue;
            if (!itemClass.isAssignableFrom(m.getReturnType())) continue;
            Class<?>[] p = m.getParameterTypes();
            if (p.length != 6 && p.length != 7) continue;
            if (p[0] != int.class || p[1] != int.class || p[2] != int.class || p[3] != int.class) continue;
            if (!CharSequence.class.isAssignableFrom(p[4]) || !CharSequence.class.isAssignableFrom(p[5])) continue;
            if (p.length == 7 && p[6] != CharSequence.class) continue;
            m.setAccessible(true);
            if (best == null || p.length > best.getParameterTypes().length) best = m;
        }
        return best;
    }

    private static Object makeTeleVipItem(Method factoryOf) throws Exception {
        Class<?>[] p = factoryOf.getParameterTypes();
        Object[] args = new Object[p.length];
        args[0] = 8353847;
        args[1] = 0xFFF46F6F;
        args[2] = 0xFFDF5555;
        args[3] = 8353847;
        args[4] = "Re: TeleVIP";
        args[5] = "by @m_1_iq & @doandat943";
        if (p.length == 7) args[6] = null;
        return factoryOf.invoke(null, args);
    }

    private static int findInsertPosition(ArrayList<?> items, Class<?> itemClass) {
        int textFallback = -1;
        for (int i = 0; i < items.size(); i++) {
            Object item = items.get(i);
            if (item == null || !itemClass.isInstance(item)) continue;
            if (getItemId(item, itemClass) == 1) return i;
            Object title = readSemanticField(item, itemClass, "text");
            Object subtitle = readSemanticField(item, itemClass, "subtext");
            if (textFallback < 0 && title != null && subtitle != null) textFallback = i;
        }
        return textFallback >= 0 ? textFallback : items.size();
    }

    private static void setTeleVipIcon(View cell, GhostDrawable drawable) {
        if (cell == null) return;
        for (Class<?> c = cell.getClass(); c != null; c = c.getSuperclass()) {
            for (java.lang.reflect.Field f : c.getDeclaredFields()) {
                if (!ImageView.class.isAssignableFrom(f.getType())) continue;
                try {
                    f.setAccessible(true);
                    ImageView image = (ImageView) f.get(cell);
                    if (image != null) {
                        image.setImageDrawable(drawable);
                        return;
                    }
                } catch (Throwable ignored) { }
            }
        }
    }

    public void newSettings(Class<?> SettingsActivityClass, Class<?> SettingsActivity$SettingCell$FactoryClass,
                            SettingsController settingsController) {
        try {
            final Class<?> itemClass = XposedHelpers.findClassIfExists(
                    Obfuscate.getClassName("org.telegram.ui.Components.UItem"), Utils.classLoader);
            final Class<?> resolvedItemClass = itemClass != null ? itemClass
                    : XposedHelpers.findClassIfExists("org.telegram.ui.Components.UItem", Utils.classLoader);
            if (resolvedItemClass == null) {
                Logger.w("SettingsHook: Graph UItem class not found; cannot hook Settings menu");
                return;
            }

            final Method fillItems = findFillItems(SettingsActivityClass);
            final Method onClick = findOnClick(SettingsActivityClass, resolvedItemClass);
            final Method factoryOf = findFactoryOf(SettingsActivity$SettingCell$FactoryClass, resolvedItemClass);
            if (fillItems == null || onClick == null || factoryOf == null) {
                Logger.w("SettingsHook: Graph hooks incomplete. fillItems=" + fillItems
                        + " onClick=" + onClick + " Factory.of=" + factoryOf);
                return;
            }

            final GhostDrawable ghostDrawable = new GhostDrawable();
            Logger.w("SettingsHook: Graph hooks resolved: " + fillItems.toGenericString()
                    + " / " + onClick.toGenericString() + " / " + factoryOf.toGenericString());

            XposedBridge.hookMethod(fillItems, new BaseMethodHook() {
                @Override
                @SuppressWarnings("unchecked")
                protected void afterMethod(final MethodHookParam param) {
                    try {
                        ArrayList<Object> list = null;
                        for (Object arg : param.args) {
                            if (arg instanceof ArrayList) {
                                list = (ArrayList<Object>) arg;
                                break;
                            }
                        }
                        if (list == null) return;
                        for (Object existing : list) {
                            if (isTeleVipItem(existing, resolvedItemClass)) return;
                        }
                        Object row = makeTeleVipItem(factoryOf);
                        if (row == null) {
                            Logger.w("SettingsHook: Graph Factory.of returned null");
                            return;
                        }
                        int index = findInsertPosition(list, resolvedItemClass);
                        list.add(Math.max(0, Math.min(index, list.size())), row);
                        Logger.w("SettingsHook: inserted Re: TeleVIP into Graph Settings at " + index);
                    } catch (Throwable t) {
                        Logger.e(t);
                    }
                }
            });

            XposedBridge.hookMethod(onClick, new BaseMethodHook() {
                @Override
                protected void afterMethod(final MethodHookParam param) {
                    try {
                        for (Object arg : param.args) {
                            if (isTeleVipItem(arg, resolvedItemClass)) {
                                Logger.w("SettingsHook: opening Re: TeleVIP from Graph Settings");
                                settingsController.openView();
                                return;
                            }
                        }
                    } catch (Throwable t) {
                        Logger.e(t);
                    }
                }
            });

            // Re: TeleVIP uses the SettingCell Factory binding lifecycle as well.
            for (Method bind : SettingsActivity$SettingCell$FactoryClass.getDeclaredMethods()) {
                Class<?>[] p = bind.getParameterTypes();
                if (bind.getReturnType() != void.class || p.length < 2
                        || !View.class.isAssignableFrom(p[0]) || !resolvedItemClass.isAssignableFrom(p[1])) continue;
                bind.setAccessible(true);
                XposedBridge.hookMethod(bind, new BaseMethodHook() {
                    @Override
                    protected void afterMethod(final MethodHookParam param) {
                        try {
                            if (param.args.length >= 2 && isTeleVipItem(param.args[1], resolvedItemClass)) {
                                setTeleVipIcon((View) param.args[0], ghostDrawable);
                            }
                        } catch (Throwable t) { Logger.e(t); }
                    }
                });
                break;
            }
        } catch (Throwable t) {
            Logger.e(t);
        }
    }

'''
hs=hs[:start]+new_method+hs[end:]
hook.write_text(hs,encoding='utf-8')

print('Applied direct Graph SettingsActivity lookup and signature-based fillItems/onClick/Factory.of hooks')
