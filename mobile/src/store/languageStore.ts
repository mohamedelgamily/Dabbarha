import { create } from 'zustand';
import { I18nManager } from 'react-native';
import Constants from 'expo-constants';
import { reloadAppAsync } from 'expo';
import * as SecureStore from 'expo-secure-store';
import { setTranslationLanguage } from '@/i18n';
import type { Language } from '@/i18n/dictionaries';

// These keys are deliberately independent of authentication storage.
export const LANGUAGE_KEY = 'dabbarha.language';
const RELOAD_KEY = 'dabbarha.language.reloadAttempt';
type LanguageState = {
  language: Language;
  ready: boolean;
  busy: boolean;
  chatProtected: boolean;
  setChatProtected: (protectedChat: boolean) => void;
  dirtyForms: Record<string, boolean>;
  setFormDirty: (id: string, dirty: boolean) => void;
  error: 'load' | 'save' | 'restart' | 'expoGo' | null;
  initialize: () => Promise<void>;
  select: (language: Language) => Promise<void>;
};

function configureDirection(language: Language) {
  const rtl = language === 'ar';
  I18nManager.allowRTL(rtl);
  I18nManager.forceRTL(rtl);
  // Use native RTL defaults; app layout edges use start/end explicitly.
  I18nManager.swapLeftAndRightInRTL(true);
}

export const useLanguageStore = create<LanguageState>((set, get) => ({
  language: 'en', ready: false, busy: false, error: null, chatProtected: false,
  setChatProtected: chatProtected => set({ chatProtected }),
  dirtyForms: {},
  setFormDirty: (id, dirty) => set(state => {
    const dirtyForms = { ...state.dirtyForms };
    if (dirty) dirtyForms[id] = true;
    else delete dirtyForms[id];
    return { dirtyForms };
  }),
  initialize: async () => {
    if (get().busy || get().ready) return;
    set({ busy: true, error: null });
    try {
      const saved = await SecureStore.getItemAsync(LANGUAGE_KEY);
      const language: Language = saved === 'ar' ? 'ar' : 'en';
      setTranslationLanguage(language);
      set({ language });
      const rtl = language === 'ar';
      if (I18nManager.isRTL !== rtl) {
        if (Constants.appOwnership === 'expo') {
          set({ error: 'expoGo', busy: false });
          return;
        }
        const attempted = await SecureStore.getItemAsync(RELOAD_KEY);
        configureDirection(language);
        if (attempted !== language) {
          await SecureStore.setItemAsync(RELOAD_KEY, language);
          try {
            await reloadAppAsync('Apply saved Dabbarha language');
          } catch {
            set({ error: 'restart', busy: false });
            return;
          }
        }
        // No recursive reload if the native host did not apply the preference.
        set({ error: 'restart', busy: false });
        return;
      }
      configureDirection(language);
      await SecureStore.deleteItemAsync(RELOAD_KEY);
      set({ ready: true, busy: false });
    } catch {
      set({ error: 'load', busy: false });
    }
  },
  select: async language => {
    if (get().busy || get().chatProtected || (language === get().language && get().ready)) return;
    if (Constants.appOwnership === 'expo' && I18nManager.isRTL !== (language === 'ar')) {
      set({ error: 'expoGo' });
      return;
    }
    set({ busy: true, error: null });
    try {
      await SecureStore.setItemAsync(LANGUAGE_KEY, language);
    } catch {
      set({ error: 'save', busy: false });
      return;
    }
    setTranslationLanguage(language);
    set({ language, ready: false });
    try {
      configureDirection(language);
      await SecureStore.setItemAsync(RELOAD_KEY, language);
      await reloadAppAsync('User changed Dabbarha language');
      set({ error: 'restart', busy: false });
    } catch {
      set({ error: 'restart', busy: false });
    }
  },
}));
