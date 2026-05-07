import { useNavigate } from "react-router-dom";
import { useUserStore } from "@/stores/userStore";
import { apiClient } from "@/services/api";
import { TrendingUp, Shield, BarChart3, Flame } from "lucide-react";
import type { RiskProfile } from "@/types";

const PROFILES: Array<{
  level: RiskProfile["level"];
  title: string;
  description: string;
  icon: typeof Shield;
  color: string;
  bg: string;
}> = [
  {
    level: "conservative",
    title: "Conservative",
    description:
      "Focus on capital preservation with stable, large-cap stocks and dividend-paying companies. " +
      "Prefers lower volatility and established businesses. Ideal for those seeking steady returns " +
      "with minimal risk exposure.",
    icon: Shield,
    color: "text-blue-400",
    bg: "border-blue-500/30 hover:border-blue-500/60 hover:bg-blue-950/30",
  },
  {
    level: "moderate",
    title: "Moderate",
    description:
      "Balanced approach combining growth and value stocks across market capitalizations. " +
      "Comfortable with moderate swings for potentially higher returns. " +
      "Suitable for investors with a medium-term horizon of 3-5 years.",
    icon: BarChart3,
    color: "text-amber-400",
    bg: "border-amber-500/30 hover:border-amber-500/60 hover:bg-amber-950/30",
  },
  {
    level: "aggressive",
    title: "Aggressive",
    description:
      "High-growth strategy targeting momentum stocks, mid/small caps, and sectoral opportunities. " +
      "Accepts higher volatility for maximum upside potential. " +
      "Best suited for experienced investors with a longer time horizon.",
    icon: Flame,
    color: "text-red-400",
    bg: "border-red-500/30 hover:border-red-500/60 hover:bg-red-950/30",
  },
];

export function OnboardingPage() {
  const setProfile = useUserStore((s) => s.setProfile);
  const navigate = useNavigate();

  const handleSelect = async (level: RiskProfile["level"]) => {
    const profile: RiskProfile = { level, preferences: {} };
    setProfile(profile);
    try {
      await apiClient.setRiskProfile(profile);
    } catch {
      // Profile saved locally; API call can be retried later
    }
    navigate("/");
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-950 px-4">
      <div className="mb-10 flex items-center gap-3">
        <TrendingUp className="h-8 w-8 text-emerald-400" />
        <h1 className="text-3xl font-bold text-white">Mr. Market</h1>
      </div>

      <h2 className="mb-2 text-xl font-semibold text-gray-200">
        Choose Your Investment Profile
      </h2>
      <p className="mb-8 max-w-md text-center text-sm text-gray-400">
        This helps Mr. Market tailor analysis and recommendations to your risk
        appetite. You can change this later.
      </p>

      <div className="grid w-full max-w-3xl gap-4 sm:grid-cols-3">
        {PROFILES.map(({ level, title, description, icon: Icon, color, bg }) => (
          <button
            key={level}
            onClick={() => handleSelect(level)}
            className={`flex flex-col items-start gap-3 rounded-xl border p-6 text-left transition-all ${bg}`}
          >
            <Icon className={`h-8 w-8 ${color}`} />
            <h3 className="text-lg font-semibold text-white">{title}</h3>
            <p className="text-sm leading-relaxed text-gray-400">{description}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
