import type { Metadata } from "next";
import { PasswordRecovery } from "../../components/PasswordRecovery";

export const metadata: Metadata = { title:"Account recovery",robots:{index:false,follow:false} };

export default function AccountRecoveryPage() {
  return <PasswordRecovery/>;
}
