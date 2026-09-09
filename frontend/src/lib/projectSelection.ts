/** Pick which show Analytics / Timeline should watch. */

export function pickProjectId(
  selected: string | null,
  projects: readonly { project_id: string }[],
): string | null {
  if (selected && projects.some((project) => project.project_id === selected)) {
    return selected;
  }
  return projects[0]?.project_id ?? null;
}
