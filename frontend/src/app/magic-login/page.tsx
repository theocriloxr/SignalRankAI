import type { Metadata } from "next";
import { MagicSignIn } from "../../components/MagicSignIn";

export const metadata: Metadata = { title:"Email sign-in",robots:{index:false,follow:false} };

export default function MagicLoginPage() {return <MagicSignIn/>;}
