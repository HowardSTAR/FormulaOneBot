import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { dataReceiptKey } from '../helpers/dataReceipt';

export function DataReceipt() {
  const location = useLocation();
  const route = dataReceiptKey(location.pathname, location.search);
  const [receipt, setReceipt] = useState<{route: string; at: number} | null>(null);
  useEffect(() => {
    const received = (event: Event) => {
      const detail = (event as CustomEvent<{route: string; at: number}>).detail;
      if (detail.route === route) setReceipt(detail);
    };
    window.addEventListener('f1hub:data-received', received);
    return () => window.removeEventListener('f1hub:data-received', received);
  }, [route]);
  if (receipt?.route !== route) return null;
  return <p className="ui-data-receipt">Данные получены: <time dateTime={new Date(receipt.at).toISOString()}>{new Date(receipt.at).toLocaleString('ru-RU')}</time></p>;
}
