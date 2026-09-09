import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'e-Maap | Government workspace',description:'Measure Compliance. Protect Consumers. Legal Metrology inspection and evidence review.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
