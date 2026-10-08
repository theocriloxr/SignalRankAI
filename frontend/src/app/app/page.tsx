import { AppShell } from "../../components/AppShell";
import { WorkspaceLive } from "../../components/WorkspaceLive";

export default function AppOverview() {
  return <AppShell active="Overview"><WorkspaceLive section="overview" /></AppShell>;
}
