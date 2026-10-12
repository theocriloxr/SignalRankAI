/** Full document navigation across the independently served workspace boundary.
 * Client-side RSC navigation cannot interpret the retained FastAPI application's HTML.
 */
export function WorkspaceLink({href,children,className}:{href:string;children:React.ReactNode;className?:string}) {
  return <a href={href} className={className}>{children}</a>;
}
