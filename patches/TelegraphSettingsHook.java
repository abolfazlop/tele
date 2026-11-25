package com.my.televip.settings.hook;

import android.content.Context;
import android.util.TypedValue;
import android.view.Gravity;
import android.widget.TextView;

import androidx.recyclerview.widget.ConcatAdapter;
import androidx.recyclerview.widget.RecyclerView;

import com.my.televip.base.BaseMethodHook;
import com.my.televip.logging.Logger;
import com.my.televip.settings.controller.SettingsController;

import java.lang.reflect.Method;
import java.util.Collections;
import java.util.Map;
import java.util.WeakHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;

/** Graph Messenger 13.2.2.2 settings integration; not Telegram SettingsActivity. */
public final class TelegraphSettingsHook {
    private static final int ROW_ID = 8353847;
    private static final String ACTIVITY = "org.telegram.ui.TelegraphSettingsActivity";
    // Exact listener class verified in the supplied 13.2.2.2 DEX.
    private static final String CLICK_LISTENER = "org.telegram.ui.pu1";
    private static final Map<RecyclerView, Boolean> installedLists =
            Collections.synchronizedMap(new WeakHashMap<RecyclerView, Boolean>());
    private static final AtomicBoolean clickHookInstalled = new AtomicBoolean(false);
    private static volatile int injectedRowPosition = -1;

    public void init(final ClassLoader classLoader, final SettingsController settingsController) {
        try {
            Class<?> activityClass = XposedHelpers.findClassIfExists(ACTIVITY, classLoader);
            if (activityClass == null) {
                Logger.w("TelegraphSettingsHook: TelegraphSettingsActivity not found");
                return;
            }
            installClickHook(classLoader, settingsController);
            XposedBridge.hookAllMethods(activityClass, "createView", new BaseMethodHook() {
                @Override
                protected void afterMethod(MethodHookParam param) {
                    try {
                        Object rawList = XposedHelpers.getObjectField(param.thisObject, "listView");
                        if (!(rawList instanceof RecyclerView)) {
                            Logger.w("TelegraphSettingsHook: listView is not a RecyclerView");
                            return;
                        }
                        RecyclerView list = (RecyclerView) rawList;
                        if (installedLists.containsKey(list)) return;
                        RecyclerView.Adapter<?> original = list.getAdapter();
                        if (original == null) {
                            Logger.w("TelegraphSettingsHook: original list adapter is null");
                            return;
                        }
                        int originalCount = original.getItemCount();
                        if (originalCount < 0) return;
                        injectedRowPosition = originalCount;
                        RecyclerView.Adapter<?> row = new TeleVipRowAdapter(list.getContext(), settingsController);
                        list.setAdapter(new ConcatAdapter(original, row));
                        installedLists.put(list, Boolean.TRUE);
                        Logger.w("TelegraphSettingsHook: Re: TeleVIP row installed at " + originalCount);
                    } catch (Throwable t) {
                        Logger.e(t);
                    }
                }
            });
            Logger.w("TelegraphSettingsHook: hooked TelegraphSettingsActivity.createView");
        } catch (Throwable t) {
            Logger.e(t);
        }
    }

    private static void installClickHook(ClassLoader classLoader, final SettingsController controller) {
        if (!clickHookInstalled.compareAndSet(false, true)) return;
        try {
            Class<?> listenerClass = XposedHelpers.findClassIfExists(CLICK_LISTENER, classLoader);
            if (listenerClass == null) {
                clickHookInstalled.set(false);
                Logger.w("TelegraphSettingsHook: pu1 listener class not found");
                return;
            }
            int count = 0;
            for (Method method : listenerClass.getDeclaredMethods()) {
                if (!"onItemClick".equals(method.getName())) continue;
                boolean hasInt = false;
                for (Class<?> p : method.getParameterTypes()) if (p == int.class) hasInt = true;
                if (!hasInt) continue;
                method.setAccessible(true);
                XposedBridge.hookMethod(method, new BaseMethodHook() {
                    @Override
                    protected void beforeMethod(MethodHookParam param) {
                        int position = Integer.MIN_VALUE;
                        for (Object arg : param.args) {
                            if (arg instanceof Integer) {
                                position = (Integer) arg;
                                break;
                            }
                        }
                        if (position == injectedRowPosition && position >= 0) {
                            controller.openView();
                            param.setResult(param.method.getReturnType() == boolean.class ? Boolean.TRUE : null);
                        }
                    }
                });
                count++;
            }
            if (count == 0) clickHookInstalled.set(false);
            Logger.w("TelegraphSettingsHook: hooked " + count + " pu1.onItemClick overload(s)");
        } catch (Throwable t) {
            clickHookInstalled.set(false);
            Logger.e(t);
        }
    }

    private static final class TeleVipRowAdapter extends RecyclerView.Adapter<RecyclerView.ViewHolder> {
        private final Context context;
        private final SettingsController controller;

        TeleVipRowAdapter(Context context, SettingsController controller) {
            this.context = context;
            this.controller = controller;
            setHasStableIds(false);
        }

        @Override public int getItemCount() { return 1; }
        @Override public int getItemViewType(int position) { return ROW_ID; }

        @Override
        public RecyclerView.ViewHolder onCreateViewHolder(android.view.ViewGroup parent, int viewType) {
            TextView row = new TextView(context);
            float density = context.getResources().getDisplayMetrics().density;
            row.setLayoutParams(new RecyclerView.LayoutParams(
                    RecyclerView.LayoutParams.MATCH_PARENT, RecyclerView.LayoutParams.WRAP_CONTENT));
            row.setMinHeight((int) (56 * density + 0.5f));
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding((int) (20 * density + 0.5f), 0, (int) (20 * density + 0.5f), 0);
            row.setText("Re: TeleVIP");
            row.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
            TypedValue color = new TypedValue();
            if (context.getTheme().resolveAttribute(android.R.attr.textColorPrimary, color, true)) {
                if (color.resourceId != 0) row.setTextColor(context.getColorStateList(color.resourceId));
                else row.setTextColor(color.data);
            }
            TypedValue background = new TypedValue();
            if (context.getTheme().resolveAttribute(android.R.attr.selectableItemBackground, background, true)
                    && background.resourceId != 0) {
                row.setBackgroundResource(background.resourceId);
            }
            row.setClickable(true);
            row.setFocusable(true);
            row.setContentDescription("Re: TeleVIP");
            return new RecyclerView.ViewHolder(row) {};
        }

        @Override
        public void onBindViewHolder(RecyclerView.ViewHolder holder, int position) {
            holder.itemView.setOnClickListener(v -> controller.openView());
        }
    }
}
