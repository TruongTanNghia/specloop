import type { Project, SpecVersion } from "../../api/types";

export interface TabProps {
  project: Project;
  specs: SpecVersion[];
  specId: number | null;
  selectSpec: (id: number) => void;
  goTab: (tab: string, specId?: number) => void;
}
