import { t, isArabic } from '@/i18n';
import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TextInput,
  ActivityIndicator,
  Alert,

  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { usePreventRemove } from 'expo-router/react-navigation';
import { useLanguageStore } from '@/store/languageStore';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { chatApi } from '@/api/chat';
import {
  ChatMessage,
  ChatResponse,
  PendingConfirmation,
} from '@/types/chat';
import { ApiErrorDetail } from '@/types/api';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Icon } from '@/components/common/Icon';
import { Logo } from '@/components/common/Logo';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { colors, typography } from '@/constants/theme';

function generateMessageId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

const getSuggestedPrompts = () => [
  t("What are my active obligations?"),
  t("Help me assess a purchase over 6 months."),
  t("What is my projected cash buffer next month?"),
  t("How much will I pay across commitments this month?"),
];

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <View
      style={[
        styles.messageRow,
        isUser ? styles.userMessageRow : styles.assistantMessageRow,
      ]}
    >
      {!isUser && (
        <View style={styles.assistantAvatar}>
          <Logo variant="symbol" tone="dark" width={16} height={16} />
        </View>
      )}

      <View
        style={[
          styles.messageBubble,
          isUser ? styles.userBubble : styles.assistantBubble,
        ]}
      >
        <Typography
          direction="auto" selectable style={isUser ? styles.userBubbleText : styles.assistantBubbleText}
        >
          {message.content}
        </Typography>
      </View>
    </View>
  );
}

interface ConfirmationCardProps {
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}

function ConfirmationCard({
  onConfirm,
  onCancel,
  isPending,
}: ConfirmationCardProps) {
  return (
    <View style={styles.confirmationCard}>
      <View style={styles.confirmationHeader}>
        <Icon name="alert-triangle" size={18} color="#D97706" />
        <Typography style={styles.confirmationTitle}>
          {t("Action requested")}</Typography>
      </View>
      <Typography style={styles.confirmationDescription}>
        {t("Review the proposed change in the response above. Confirm only when you are ready to update your financial records.")}</Typography>
      <View style={styles.confirmationButtons}>
        <Button
          title={t("Confirm")}
          onPress={onConfirm}
          isLoading={isPending}
          style={styles.confirmButton}
        />
        <Button
          title={t("Cancel")}
          variant="secondary"
          onPress={onCancel}
          disabled={isPending}
          style={styles.cancelButton}
        />
      </View>
    </View>
  );
}

export default function ChatScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const scrollViewRef = useRef<ScrollView>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] =
    useState<PendingConfirmation | null>(null);
  const [cancelledMessage, setCancelledMessage] = useState<string | null>(null);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, []);

  const mutation = useMutation<
    ChatResponse,
    { statusCode: number; message: string; detail?: string | ApiErrorDetail[] },
    { message: string; confirmationToolKey?: string | null }
  >({
    mutationFn: async ({ message, confirmationToolKey }) => {
      return chatApi.sendMessage({
        message,
        conversation_id: conversationId,
        confirmationToolKey,
      });
    },
    onSuccess: (data, variables) => {
      setConversationId(data.conversation_id);
      setInputText('');

      const metadata = data.metadata || {};

      if (metadata.pending_confirmation) {
        setPendingConfirmation({
          key: metadata.pending_confirmation,
          message: variables.message,
          conversationId: data.conversation_id,
        });
      } else {
        setPendingConfirmation(null);

        if (metadata.tool && metadata.status === 'executed') {
          queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
          queryClient.invalidateQueries({ queryKey: ['obligations'] });
          queryClient.invalidateQueries({ queryKey: ['forecast'] });
        }

        if (metadata.error === 'conversation_not_found') {
          setConversationId(null);
        }
      }

      setMessages((prev) => [
        ...prev,
        {
          id: generateMessageId(),
          role: 'assistant',
          content: data.response,
        },
      ]);
    },
    onError: (err) => {
      setApiError(err?.message || t("Failed to send message. Please try again."));
    },
  });

  const chatProtected = mutation.isPending || !!pendingConfirmation;
  useEffect(() => {
    useLanguageStore.getState().setChatProtected(chatProtected);
    return () => useLanguageStore.getState().setChatProtected(false);
  }, [chatProtected]);
  usePreventRemove(chatProtected, () => {
    Alert.alert(t('Action requested'), t('Finish or cancel the pending chat action before leaving or changing language.'));
  });

  const handleSendPrompt = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || mutation.isPending) return;

    setApiError(null);
    setCancelledMessage(null);
    setMessages((prev) => [
      ...prev,
      {
        id: generateMessageId(),
        role: 'user',
        content: trimmed,
      },
    ]);
    scrollToBottom();

    mutation.mutate(
      { message: trimmed },
      {
        onSuccess: () => {
          scrollToBottom();
        },
      }
    );
  };

  const handleConfirm = () => {
    if (!pendingConfirmation || mutation.isPending) return;

    setApiError(null);
    setMessages((prev) => [
      ...prev,
      {
        id: generateMessageId(),
        role: 'user',
        content: pendingConfirmation.message,
      },
    ]);
    scrollToBottom();

    mutation.mutate(
      {
        message: pendingConfirmation.message,
        confirmationToolKey: pendingConfirmation.key,
      },
      {
        onSuccess: () => {
          scrollToBottom();
        },
      }
    );
  };

  const handleCancel = () => {
    if (!pendingConfirmation) return;
    setCancelledMessage(t("Action cancelled."));
    setPendingConfirmation(null);
    scrollToBottom();
  };

  return (
    <ScreenWrapper edges={['top', 'bottom', 'left', 'right']} backgroundColor={colors.primary} statusBarStyle="light">
      <View style={styles.container}>
        {/* Top Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            onPress={() => router.back()}
            style={styles.backTouch}
            accessibilityRole="button"
            accessibilityLabel={t("Back")}
          >
            <Icon name="arrow-left" size={20} color="#E4EDE2" />
          </TouchableOpacity>

          <View style={styles.headerTitleRow}>
            <View style={styles.headerSymbolBadge}>
              <Logo variant="symbol" tone="light" width={22} height={22} />
            </View>
            <View>
              <Typography style={styles.headerTitle}>Dabbarha</Typography>
              <View style={styles.statusLiveRow}>

                <Typography style={styles.statusLiveText}>{t("Financial Copilot")}</Typography>
              </View>
            </View>
          </View>

          <View style={{ width: 36 }} />
        </View>

        <ErrorBanner
          message={apiError}
          onDismiss={() => setApiError(null)}
          style={styles.errorBanner}
        />

        {/* Messages List */}
        <ScrollView
          ref={scrollViewRef}
          style={styles.messagesContainer}
          contentContainerStyle={styles.messagesContent}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => scrollToBottom()}
        >
          {messages.length === 0 && !pendingConfirmation && (
            <View style={styles.emptyState}>
              <View style={styles.copilotBadge}>
                <Logo variant="symbol" tone="dark" width={32} height={32} />
              </View>
              <Typography style={styles.emptyHeading}>
                {t("Ask Dabbarha")}</Typography>
              <Typography style={styles.emptySubtitle}>
                {t("Plan your money with context. Ask about commitments, cashflow, affordability, or your next financial decision.")}</Typography>

              <Typography variant="caption">{t('Replies are provided by the assistant and may use a different language.')}</Typography>
              {/* Suggested Prompt Chips */}
              <View style={styles.promptsContainer}>
                <Typography style={styles.promptsLabel}>
                  {t("Start with a question")}</Typography>
                {getSuggestedPrompts().map((prompt, idx) => (
                  <TouchableOpacity
                    key={idx}
                    activeOpacity={0.75}
                    onPress={() => handleSendPrompt(prompt)}
                    style={styles.promptChip} accessibilityRole="button"
                  >
                    <View style={styles.promptIcon}><Icon name={(['credit-card', 'pie-chart', 'trending-up', 'calendar'] as const)[idx]} size={18} color="#4D7E6A" /></View>
                    <Typography style={styles.promptChipText}>
                      {prompt}
                    </Typography>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {!mutation.isPending && !pendingConfirmation && mutation.data?.metadata?.tool &&
            (mutation.data.metadata.status === 'executed' || mutation.data.metadata.status === 'error') && (
            <View style={[styles.resultNotice, mutation.data.metadata.status === 'error' && styles.resultError]} accessibilityLiveRegion="polite">
              <Icon name={mutation.data.metadata.status === 'executed' ? 'check-circle' : 'alert-triangle'} size={17} color="#6C7756" />
              <Typography style={styles.resultText}>{mutation.data.metadata.status === 'executed' ? t("Financial action completed.") : t("The financial action could not be completed. See Dabbarha’s response for details.")}</Typography>
            </View>
          )}
          {!mutation.isPending && mutation.data?.metadata?.error && (
            <View style={styles.resultNotice}>
              <Typography style={styles.resultText}>{mutation.data.metadata.error === 'conversation_not_found'
                ? t("This conversation is no longer available. Your next message will start a new conversation.")
                : t("Dabbarha could not finish this request. Please try again.")}</Typography>
            </View>
          )}
          {cancelledMessage && (
            <View style={styles.cancelledIndicator}>
              <Typography variant="caption" color={colors.textSecondary}>
                {cancelledMessage}
              </Typography>
            </View>
          )}

          {pendingConfirmation && (
            <ConfirmationCard
              onConfirm={handleConfirm}
              onCancel={handleCancel}
              isPending={mutation.isPending}
            />
          )}

          {mutation.isPending && (
            <View style={styles.typingIndicator}>
              <View style={styles.assistantAvatar}>
                <Logo variant="symbol" tone="dark" width={14} height={14} />
              </View>
              <View style={styles.typingBubble} accessibilityLiveRegion="polite"><ActivityIndicator size="small" color="#658776" />
                <Typography style={styles.typingText}>
                  {t("Thinking through your request…")}</Typography>
              </View>
            </View>
          )}
        </ScrollView>

        {/* Input Bar */}
        <View style={styles.inputContainer}>
          <TextInput
            style={[styles.textInput, { textAlign: 'left', direction: isArabic() ? 'rtl' : 'ltr', writingDirection: 'auto' }, isArabic() && { fontFamily: 'NotoNaskhArabic', lineHeight: 27 }]}
            value={inputText}
            onChangeText={setInputText}
            placeholder={t("Ask Dabbarha anything...")} accessibilityLabel={t("Message Dabbarha")}
            placeholderTextColor={colors.textMuted}
            multiline
            maxLength={1000}
            editable={!mutation.isPending}
          />
          <TouchableOpacity
            onPress={() => handleSendPrompt(inputText)}
            disabled={!inputText.trim() || mutation.isPending}
            style={[
              styles.sendButton,
              (!inputText.trim() || mutation.isPending) &&
                styles.sendButtonDisabled,
            ]}
            activeOpacity={0.75} accessibilityRole="button" accessibilityLabel={t("Send message")}
          >
            <Icon
              name="send"
              size={18}
              color={
                !inputText.trim() || mutation.isPending
                  ? colors.textMuted
                  : colors.textInverse
              }
            />
          </TouchableOpacity>
        </View>
      </View>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F6F4EF' },
  topHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: 17, paddingTop: 10, paddingBottom: 17, backgroundColor: '#02262D', borderBottomLeftRadius: 23, borderBottomRightRadius: 23 },
  backTouch: { width: 40, height: 44, borderRadius: 20, backgroundColor: '#174041', alignItems: 'center', justifyContent: 'center' },
  headerTitleRow: { flex: 1, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 11 },
  headerSymbolBadge: { width: 35, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { ...typography.title, fontSize: 23, lineHeight: 30, color: '#F5F5E9' },
  statusLiveRow: { flexDirection: 'row', alignItems: 'center' },
  statusLiveText: { fontSize: 11, lineHeight: 17, color: '#ACC8BA' },
  errorBanner: { marginHorizontal: 16, marginTop: 8 },
  messagesContainer: { flex: 1 },
  messagesContent: { paddingHorizontal: 18, paddingTop: 21, paddingBottom: 22, flexGrow: 1 },
  emptyState: { paddingTop: 13, paddingBottom: 14 },
  copilotBadge: { width: 68, height: 68, borderRadius: 24, backgroundColor: '#E3EDE1', borderWidth: 1, borderColor: '#BECFBB', alignItems: 'center', justifyContent: 'center', marginBottom: 18, transform: [{ rotate: '-4deg' }] },
  emptyHeading: { ...typography.title, fontSize: 32, lineHeight: 41, color: '#234D40' },
  emptySubtitle: { fontSize: 14, lineHeight: 23, color: '#75877A', marginTop: 9, maxWidth: 370 },
  promptsContainer: { marginTop: 25, gap: 9 },
  promptsLabel: { ...typography.title, fontSize: 15, lineHeight: 22, color: '#3E5C4D', marginBottom: 3 },
  promptChip: { flexDirection: 'row', gap: 12, alignItems: 'center', padding: 12, minHeight: 58, borderRadius: 17, backgroundColor: '#FCFBF7', borderWidth: 1, borderColor: '#E5E9DE' },
  promptIcon: { width: 33, height: 33, borderRadius: 11, backgroundColor: '#EAF0E4', alignItems: 'center', justifyContent: 'center' },
  promptChipText: { flex: 1, fontSize: 13, lineHeight: 20, color: '#375B4B' },
  messageRow: { flexDirection: 'row', marginBottom: 23, gap: 9, alignItems: 'flex-start' },
  userMessageRow: { justifyContent: 'flex-end' },
  assistantMessageRow: { justifyContent: 'flex-start' },
  assistantAvatar: { width: 29, height: 32, borderRadius: 11, backgroundColor: '#E4EDE0', alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  messageBubble: { flexShrink: 1, minWidth: 0 },
  userBubble: { maxWidth: '87%', backgroundColor: '#073A39', paddingVertical: 12, paddingHorizontal: 16, borderRadius: 21, borderEndEndRadius: 6 },
  assistantBubble: { flex: 1, paddingVertical: 5, paddingEnd: 3 },
  userBubbleText: { fontSize: 15, lineHeight: 24, color: '#F2F5EA', fontVariant: ['tabular-nums'] },
  assistantBubbleText: { fontSize: 15, lineHeight: 25, color: '#29483D', fontVariant: ['tabular-nums'] },
  confirmationCard: { backgroundColor: '#F1EBD8', borderWidth: 1, borderColor: '#D9CAA1', borderRadius: 20, padding: 18, marginTop: 4, marginBottom: 19 },
  confirmationHeader: { flexDirection: 'row', gap: 9, alignItems: 'center', marginBottom: 9 },
  confirmationTitle: { ...typography.title, fontSize: 20, lineHeight: 27, color: '#625333', flexShrink: 1 },
  confirmationDescription: { fontSize: 13, lineHeight: 21, color: '#7D735A', marginBottom: 17 },
  confirmationButtons: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 10 },
  confirmButton: { flex: 1, minWidth: 110, minHeight: 47 },
  cancelButton: { flex: 1, minWidth: 110, minHeight: 47, backgroundColor: '#E5DDC7' },
  cancelledIndicator: { alignItems: 'center', paddingVertical: 10, marginBottom: 12 },
  resultNotice: { flexDirection: 'row', gap: 8, padding: 12, borderRadius: 12, backgroundColor: '#E4EDDF', marginBottom: 15 },
  resultError: { backgroundColor: '#F0E5D9' },
  resultText: { flex: 1, fontSize: 12, lineHeight: 19, color: '#667458' },
  typingIndicator: { flexDirection: 'row', gap: 9, alignItems: 'center', marginTop: 2, marginBottom: 14 },
  typingBubble: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 9, paddingVertical: 12 },
  typingText: { fontSize: 12, lineHeight: 19, color: '#6D8674', flexShrink: 1 },
  inputContainer: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, backgroundColor: '#FBFAF5', borderTopWidth: 1, borderTopColor: '#DEE5D6', paddingHorizontal: 16, paddingTop: 12, paddingBottom: 13 },
  textInput: { fontFamily: typography.fontFamily, flex: 1, minHeight: 48, maxHeight: 135, backgroundColor: '#F4F4ED', borderWidth: 1, borderColor: '#DBE2D4', borderRadius: 21, paddingHorizontal: 15, paddingTop: 12, paddingBottom: 12, fontSize: 15, lineHeight: 22, color: '#23463C' },
  sendButton: { width: 46, height: 46, borderRadius: 23, backgroundColor: '#02262D', alignItems: 'center', justifyContent: 'center', marginBottom: 1 },
  sendButtonDisabled: { backgroundColor: '#E1E7DB' },
});
