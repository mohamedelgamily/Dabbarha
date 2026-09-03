import React from 'react';
import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  Bell,
  Calendar,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock,
  CreditCard,
  DollarSign,
  Eye,
  EyeOff,
  FileText,
  Filter,
  Hash,
  HelpCircle,
  Home,
  ListChecks,
  Loader2,
  Lock,
  LogOut,
  Mail,
  MessageCircle,
  MoreHorizontal,
  PieChart,
  Plus,
  RefreshCcw,
  Search,
  Send,
  Settings,
  TrendingUp,
  User,
  Wallet,
  X,
  type LucideIcon,
} from 'lucide-react-native';
import { colors } from '@/constants/theme';

export type IconName =
  | 'alert-triangle'
  | 'arrow-down'
  | 'arrow-left'
  | 'bell'
  | 'calendar'
  | 'check'
  | 'check-circle'
  | 'chevron-right'
  | 'circle'
  | 'clock'
  | 'credit-card'
  | 'dollar-sign'
  | 'eye'
  | 'eye-off'
  | 'file-text'
  | 'filter'
  | 'hash'
  | 'help'
  | 'home'
  | 'list-checks'
  | 'loader'
  | 'lock'
  | 'logout'
  | 'mail'
  | 'message-circle'
  | 'more-horizontal'
  | 'pie-chart'
  | 'plus'
  | 'refresh'
  | 'search'
  | 'send'
  | 'settings'
  | 'trending-up'
  | 'user'
  | 'wallet'
  | 'x';

const ICONS: Record<IconName, LucideIcon> = {
  'alert-triangle': AlertTriangle,
  'arrow-down': ArrowDown,
  'arrow-left': ArrowLeft,
  bell: Bell,
  calendar: Calendar,
  check: Check,
  'check-circle': CheckCircle2,
  'chevron-right': ChevronRight,
  circle: Circle,
  clock: Clock,
  'credit-card': CreditCard,
  'dollar-sign': DollarSign,
  eye: Eye,
  'eye-off': EyeOff,
  'file-text': FileText,
  filter: Filter,
  hash: Hash,
  help: HelpCircle,
  home: Home,
  'list-checks': ListChecks,
  loader: Loader2,
  lock: Lock,
  logout: LogOut,
  mail: Mail,
  'message-circle': MessageCircle,
  'more-horizontal': MoreHorizontal,
  'pie-chart': PieChart,
  plus: Plus,
  refresh: RefreshCcw,
  search: Search,
  send: Send,
  settings: Settings,
  'trending-up': TrendingUp,
  user: User,
  wallet: Wallet,
  x: X,
};

export type IconTone = 'primary' | 'secondary' | 'muted' | 'inverse' | 'success' | 'warning' | 'error' | 'info';

const TONE_COLOR: Record<IconTone, string> = {
  primary: colors.primary,
  secondary: colors.secondary,
  muted: colors.textMuted,
  inverse: colors.textInverse,
  success: colors.success,
  warning: colors.warning,
  error: colors.error,
  info: colors.info,
};

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  tone?: IconTone;
  strokeWidth?: number;
  style?: React.ComponentProps<LucideIcon>['style'];
}

export function Icon({
  name,
  size = 20,
  color,
  tone = 'primary',
  strokeWidth = 1.75,
  style,
}: IconProps) {
  const Component = ICONS[name];
  if (!Component) return null;
  return (
    <Component
      size={size}
      color={color ?? TONE_COLOR[tone]}
      strokeWidth={strokeWidth}
      style={style}
    />
  );
}
