import type { Metadata } from "next";

import { MaeSaiCommandExercise } from "@/components/mae-sai-command-exercise";

export const metadata: Metadata = {
  title: "Command exercise replay: Mae Sai, September 2024",
  description: "An exercise and after-action replay of the September 2024 Mae Sai flood for people who coordinate rescue: a full-screen map that steps through 9 to 19 September hour by hour, with modelled water, modelled road inundation and the shelters reported in use. Reconstructed, not real-time, and not an official warning; every modelled figure is low confidence.",
};

export default function CommandExercisePage() {
  return <MaeSaiCommandExercise />;
}
