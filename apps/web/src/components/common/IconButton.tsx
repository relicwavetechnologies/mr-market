import type { LucideIcon } from "lucide-react";

interface IconButtonProps {
  icon: LucideIcon;
  onClick?: () => void;
  className?: string;
  size?: number;
  label?: string;
  disabled?: boolean;
}

export function IconButton({
  icon: Icon,
  onClick,
  className = "",
  size = 18,
  label,
  disabled = false,
}: IconButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={`flex items-center justify-center rounded-lg p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
    >
      <Icon size={size} />
    </button>
  );
}
