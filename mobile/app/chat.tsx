import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { chatApi } from '@/api/chat';
import { ChatMessage, ChatResponse } from '@/types/chat';
import { ApiErrorDetail } from '@/types/api';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { colors, spacing, borderRadius } from '@/constants/theme';

function generateMessageId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <View
      style={[
        styles.messageBubble,
        isUser ? styles.userBubble : styles.assistantBubble,
      ]}
    >
      <Typography
        variant="body"
        color={isUser ? colors.textInverse : colors.textPrimary}
      >
        {message.content}
      </Typography>
    </View>
  );
}

export default function ChatScreen() {
  const router = useRouter();
  const scrollViewRef = useRef<ScrollView>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const mutation = useMutation<
    ChatResponse,
    { statusCode: number; message: string; detail?: string | ApiErrorDetail[] },
    string
  >({
    mutationFn: async (message) => {
      return chatApi.sendMessage({
        message,
        conversation_id: conversationId,
      });
    },
    onSuccess: (data) => {
      setConversationId(data.conversation_id);
      setInputText('');
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
      setApiError(err?.message || 'Failed to send message. Please try again.');
    },
  });

  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, []);

  const handleSend = () => {
    const trimmed = inputText.trim();
    if (!trimmed || mutation.isPending) {
      return;
    }

    setApiError(null);
    setMessages((prev) => [
      ...prev,
      {
        id: generateMessageId(),
        role: 'user',
        content: trimmed,
      },
    ]);
    scrollToBottom();

    mutation.mutate(trimmed, {
      onSuccess: () => {
        scrollToBottom();
      },
    });
  };

  return (
    <ScreenWrapper edges={['top']}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        <View style={styles.header}>
          <Typography variant="h1">Dabbarha Assistant</Typography>
        </View>

        <ErrorBanner
          message={apiError}
          onDismiss={() => setApiError(null)}
          style={styles.errorBanner}
        />

        <ScrollView
          ref={scrollViewRef}
          style={styles.messagesContainer}
          contentContainerStyle={styles.messagesContent}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => scrollToBottom()}
        >
          {messages.length === 0 && (
            <View style={styles.emptyState}>
              <Typography variant="body" color={colors.textSecondary} align="center">
                Ask me anything about your finances, obligations, or budgeting.
              </Typography>
            </View>
          )}

          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {mutation.isPending && (
            <View style={styles.typingIndicator}>
              <Typography variant="caption" color={colors.textSecondary}>
                Dabbarha is typing...
              </Typography>
            </View>
          )}
        </ScrollView>

        <View style={styles.inputContainer}>
          <TextInput
            style={styles.textInput}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Type your message..."
            placeholderTextColor={colors.textMuted}
            multiline
            maxLength={1000}
            editable={!mutation.isPending}
          />
          <TouchableOpacity
            onPress={handleSend}
            disabled={!inputText.trim() || mutation.isPending}
            style={[
              styles.sendButton,
              (!inputText.trim() || mutation.isPending) &&
                styles.sendButtonDisabled,
            ]}
            activeOpacity={0.7}
          >
            <Typography
              variant="bodyBold"
              color={
                !inputText.trim() || mutation.isPending
                  ? colors.textMuted
                  : colors.textInverse
              }
            >
              Send
            </Typography>
          </TouchableOpacity>
        </View>

        <Button
          title="Back to Dashboard"
          variant="secondary"
          onPress={() => router.back()}
          style={styles.backButton}
        />
      </KeyboardAvoidingView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  errorBanner: {
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
  },
  messagesContainer: {
    flex: 1,
  },
  messagesContent: {
    padding: spacing.md,
    flexGrow: 1,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: spacing.xxl,
  },
  messageBubble: {
    maxWidth: '80%',
    padding: spacing.sm,
    borderRadius: borderRadius.lg,
    marginBottom: spacing.sm,
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: colors.primary,
    borderBottomRightRadius: borderRadius.sm,
  },
  assistantBubble: {
    alignSelf: 'flex-start',
    backgroundColor: colors.surfaceAlt,
    borderBottomLeftRadius: borderRadius.sm,
  },
  typingIndicator: {
    alignSelf: 'flex-start',
    padding: spacing.xs,
    marginBottom: spacing.sm,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
    gap: spacing.sm,
  },
  textInput: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 16,
    color: colors.textPrimary,
    backgroundColor: colors.background,
  },
  sendButton: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.lg,
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: 44,
  },
  sendButtonDisabled: {
    backgroundColor: colors.surfaceAlt,
  },
  backButton: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
  },
});
