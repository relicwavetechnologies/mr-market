interface Props {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE_CLASSES = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
  lg: "h-10 w-10 border-3",
};

export function LoadingSpinner({ size = "md", className = "" }: Props) {
  return (
    <div
      className={`animate-spin rounded-full border-gray-700 border-t-emerald-500 ${SIZE_CLASSES[size]} ${className}`}
      role="status"
      aria-label="Loading"
    />
  );
}
