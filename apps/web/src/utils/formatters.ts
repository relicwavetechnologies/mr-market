export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatTimestamp(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay === 1) return 'Yesterday';
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

export function groupByDate<T extends { updatedAt: Date }>(items: T[]): Record<string, T[]> {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const sevenDaysAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
  const thirtyDaysAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);

  const groups: Record<string, T[]> = {};

  for (const item of items) {
    const itemDate = new Date(item.updatedAt);
    let label: string;

    if (itemDate >= today) {
      label = 'Today';
    } else if (itemDate >= sevenDaysAgo) {
      label = 'Previous 7 Days';
    } else if (itemDate >= thirtyDaysAgo) {
      label = 'Previous 30 Days';
    } else {
      label = 'Older';
    }

    if (!groups[label]) {
      groups[label] = [];
    }
    groups[label].push(item);
  }

  return groups;
}
