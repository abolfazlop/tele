package com.my.televip.settings.hook;

import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.recyclerview.widget.RecyclerView;

import com.my.televip.Drawable.GhostDrawable;
import com.my.televip.base.BaseMethodHook;
import com.my.televip.logging.Logger;
import com.my.televip.settings.controller.SettingsController;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Map;
import java.util.WeakHashMap;

import de.robv.android.xposed.XposedHelpers;

/**
 * Graph Messenger 13.2.2.2 only.
 * Mirrors Re: TeleVIP's row-insertion model: shift the host screen's row indices,
 * bind the inserted row with the native Account-row cell, relabel it, and intercept
 * only the injected click position. No extra adapter is created.
 */
public final class GraphProfileSettingsHook {
    private static final String PROFILE = "org.telegram.ui.ProfileActivity";
    private static final String ADAPTER = "org.telegram.ui.ai1";
    private static final String CLICK_LISTENER = "org.telegram.ui.yf1";
    private static final String ROW_TITLE = "Re: TeleVIP";
    private static final String ROW_SUBTITLE = "by @m_1_iq & @doandat943";

    // Integer row-position fields read by Graph 13.2.2.2's ai1 adapter.
    private static final String[] ROW_FIELDS = {
            "addMemberRow", "addToContactsRow", "addToGroupButtonRow", "addToGroupInfoRow",
            "adminOptionsRow", "administratorsRow", "affiliateRow", "balanceDividerRow",
            "bioRow", "bizHoursRow", "bizLocationRow", "blockedUsersRow", "botAppRow",
            "botOperationsRow", "botPermissionBiometry", "botPermissionEmojiStatus",
            "botPermissionLocation", "botStarsBalanceRow", "botTonBalanceRow", "bottomPaddingRow",
            "businessRow", "channelBalanceRow", "channelBalanceSectionRow", "channelDividerRow",
            "channelInfoRow", "channelRow", "chatRow", "clearLogsRow", "dataRow", "debugHeaderRow",
            "deleteReactionRow", "devicesRow", "devicesSectionRow", "emptyRow", "emptyRow2",
            "faqRow", "filtersRow", "graceSuggestionRow", "graceSuggestionSectionRow", "helpHeaderRow",
            "infoAffiliateRow", "infoHeaderRow", "infoSectionRow", "joinRow", "languageRow",
            "lastSectionRow", "linkedCommunityDividerRow", "linkedCommunityRow", "liteModeRow",
            "locationRow", "membersEndRow", "membersFilterRow", "membersHeaderRow", "membersSectionRow",
            "membersStartRow", "noteRow", "notificationRow", "notificationsDividerRow", "notificationsRow",
            "notificationsSimpleRow", "numberRow", "numberSectionRow", "R4", "v2", "w2", "passwordSuggestionRow",
            "passwordSuggestionSectionRow", "phoneRow", "phoneSuggestionRow", "phoneSuggestionSectionRow",
            "policyRow", "premiumGiftingRow", "premiumRow", "premiumSectionsRow", "privacyRow",
            "questionRow", "reportDividerRow", "reportReactionRow", "reportRow", "secretSettingsSectionRow",
            "sendLastLogsRow", "sendLogsRow", "sendMessageRow", "setAvatarRow", "setAvatarSectionRow",
            "setUsernameRow", "settingsKeyRow", "settingsRow", "settingsSectionRow", "settingsSectionRow2",
            "settingsTimerRow", "sharedMediaRow", "starsRow", "stickersRow", "subscribersRequestsRow",
            "subscribersRow", "switchBackendRow", "tonRow", "unblockRow", "unofficialSecurityRiskDividerRow",
            "unofficialSecurityRiskRow", "userInfoRow", "userLanguageRow", "usernameRow", "versionRow"
    };

    private static final Map<Object, State> STATES =
            Collections.synchronizedMap(new WeakHashMap<Object, State>());

    private final SettingsController settingsController;

    public GraphProfileSettingsHook(SettingsController settingsController) {
        this.settingsController = settingsController;
    }

    public void install(ClassLoader loader) {
        try {
            final Class<?> profileClass = XposedHelpers.findClassIfExists(PROFILE, loader);
            final Class<?> adapterClass = XposedHelpers.findClassIfExists(ADAPTER, loader);
            final Class<?> clickClass = XposedHelpers.findClassIfExists(CLICK_LISTENER, loader);
            if (profileClass == null || adapterClass == null || clickClass == null) {
                Logger.w("GraphProfileSettingsHook: Graph classes missing: ProfileActivity="
                        + profileClass + ", adapter=" + adapterClass + ", click=" + clickClass);
                return;
            }

            XposedHelpers.findAndHookMethod(profileClass, "p6", new BaseMethodHook() {
                @Override
                protected void afterMethod(MethodHookParam param) {
                    injectRow(param.thisObject);
                }
            });

            XposedHelpers.findAndHookMethod(adapterClass, "getItemCount", new BaseMethodHook() {
                @Override
                protected void afterMethod(MethodHookParam param) {
                    State state = stateForAdapter(param.thisObject);
                    if (state != null && state.index >= 0 && param.getResult() instanceof Integer) {
                        param.setResult(((Integer) param.getResult()) + 1);
                    }
                }
            });

            XposedHelpers.findAndHookMethod(adapterClass, "getItemViewType", int.class, new BaseMethodHook() {
                @Override
                protected void afterMethod(MethodHookParam param) {
                    State state = stateForAdapter(param.thisObject);
                    if (state == null || state.index < 0 || ((Integer) param.args[0]) != state.index) return;
                    int type = resolveAccountRowType(param.thisObject, state);
                    if (type != Integer.MIN_VALUE) param.setResult(type);
                }
            });

            XposedHelpers.findAndHookMethod(adapterClass, "onBindViewHolder",
                    RecyclerView.ViewHolder.class, int.class, new BaseMethodHook() {
                        @Override
                        protected void beforeMethod(MethodHookParam param) {
                            State state = stateForAdapter(param.thisObject);
                            if (state == null || state.index < 0 || ((Integer) param.args[1]) != state.index) return;
                            param.setObjectExtra("tele_vip_graph_row", Boolean.TRUE);
                            // Bind the original Account row with its native Graph cell, then relabel it.
                            param.args[1] = state.index + 1;
                        }

                        @Override
                        protected void afterMethod(MethodHookParam param) {
                            if (!Boolean.TRUE.equals(param.getObjectExtra("tele_vip_graph_row"))) return;
                            try {
                                RecyclerView.ViewHolder holder = (RecyclerView.ViewHolder) param.args[0];
                                styleInjectedRow(holder.itemView);
                            } catch (Throwable t) {
                                Logger.e(t);
                            }
                        }
                    });

            XposedHelpers.findAndHookMethod(adapterClass, "isEnabled", RecyclerView.ViewHolder.class,
                    new BaseMethodHook() {
                        @Override
                        protected void afterMethod(MethodHookParam param) {
                            State state = stateForAdapter(param.thisObject);
                            if (state == null || state.index < 0) return;
                            RecyclerView.ViewHolder holder = (RecyclerView.ViewHolder) param.args[0];
                            if (holder.getAdapterPosition() == state.index) param.setResult(Boolean.TRUE);
                        }
                    });

            XposedHelpers.findAndHookMethod(clickClass, "onItemClick", View.class, int.class,
                    new BaseMethodHook() {
                        @Override
                        protected void beforeMethod(MethodHookParam param) {
                            Object activity = getFieldValue(param.thisObject, "c");
                            State state = activity == null ? null : STATES.get(activity);
                            if (state == null || state.index < 0 || ((Integer) param.args[1]) != state.index) return;
                            settingsController.openView();
                            param.setResult(Boolean.TRUE);
                        }
                    });

            Logger.w("GraphProfileSettingsHook: installed Graph 13.2.2.2 ProfileActivity/ai1/yf1 hooks");
        } catch (Throwable t) {
            Logger.e(t);
        }
    }

    private void injectRow(Object activity) {
        try {
            int currentAccountRow = readIntField(activity, "numberRow");
            if (currentAccountRow < 0) {
                Logger.w("GraphProfileSettingsHook: numberRow (Account row) is not initialized");
                return;
            }
            State old = STATES.get(activity);
            // p6 may rebuild row positions; a shifted value means this screen is already patched.
            if (old != null && currentAccountRow == old.index + 1) return;

            for (String name : ROW_FIELDS) {
                Field f = findField(activity.getClass(), name);
                if (f == null || f.getType() != int.class) continue;
                f.setAccessible(true);
                int value = f.getInt(activity);
                if (value >= currentAccountRow) f.setInt(activity, value + 1);
            }

            State state = new State(currentAccountRow);
            STATES.put(activity, state);
            Object adapter = getFieldValue(activity, "b");
            if (adapter != null) {
                state.accountViewType = invokeInt(adapter, "getItemViewType", currentAccountRow + 1);
                invokeNoArgs(adapter, "notifyDataSetChanged");
            }
            Logger.w("GraphProfileSettingsHook: inserted Re: TeleVIP after Accounts heading and before Account at row "
                    + currentAccountRow + ", native cell type=" + state.accountViewType);
        } catch (Throwable t) {
            Logger.e(t);
        }
    }

    private static State stateForAdapter(Object adapter) {
        Object activity = getFieldValue(adapter, "k");
        return activity == null ? null : STATES.get(activity);
    }

    private static int resolveAccountRowType(Object adapter, State state) {
        if (state.accountViewType != Integer.MIN_VALUE) return state.accountViewType;
        int value = invokeInt(adapter, "getItemViewType", state.index + 1);
        state.accountViewType = value;
        return value;
    }

    private static void styleInjectedRow(View root) {
        ArrayList<TextView> texts = new ArrayList<>();
        ArrayList<ImageView> images = new ArrayList<>();
        collectViews(root, texts, images);
        if (!texts.isEmpty()) texts.get(0).setText(ROW_TITLE);
        if (texts.size() > 1) texts.get(1).setText(ROW_SUBTITLE);
        if (!images.isEmpty()) images.get(0).setImageDrawable(new GhostDrawable());
        root.setEnabled(true);
        root.setClickable(true);
        root.setContentDescription(ROW_TITLE + ", " + ROW_SUBTITLE);
    }

    private static void collectViews(View view, ArrayList<TextView> texts, ArrayList<ImageView> images) {
        if (view instanceof TextView) texts.add((TextView) view);
        if (view instanceof ImageView) images.add((ImageView) view);
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) collectViews(group.getChildAt(i), texts, images);
        }
    }

    private static int invokeInt(Object receiver, String name, int arg) {
        try {
            Method method = receiver.getClass().getMethod(name, int.class);
            method.setAccessible(true);
            Object result = method.invoke(receiver, arg);
            return result instanceof Number ? ((Number) result).intValue() : Integer.MIN_VALUE;
        } catch (Throwable t) {
            Logger.e(t);
            return Integer.MIN_VALUE;
        }
    }

    private static void invokeNoArgs(Object receiver, String name) {
        try {
            Method method = receiver.getClass().getMethod(name);
            method.setAccessible(true);
            method.invoke(receiver);
        } catch (Throwable t) {
            Logger.e(t);
        }
    }

    private static int readIntField(Object object, String name) throws Exception {
        Field f = findField(object.getClass(), name);
        if (f == null) throw new NoSuchFieldException(name);
        f.setAccessible(true);
        return f.getInt(object);
    }

    private static Object getFieldValue(Object object, String name) {
        if (object == null) return null;
        try {
            Field f = findField(object.getClass(), name);
            if (f == null) return null;
            f.setAccessible(true);
            return f.get(object);
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static Field findField(Class<?> type, String name) {
        for (Class<?> c = type; c != null; c = c.getSuperclass()) {
            try {
                return c.getDeclaredField(name);
            } catch (NoSuchFieldException ignored) { }
        }
        return null;
    }

    private static final class State {
        final int index;
        volatile int accountViewType = Integer.MIN_VALUE;
        State(int index) { this.index = index; }
    }
}
