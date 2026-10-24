import { useSearchParams } from 'react-router-dom';
import { homeSectionFromSearch } from '../../helpers/homeSections';
export { homeSections as sections, type HomeSection } from '../../helpers/homeSections';

export function useHomeSection() {
  const [params] = useSearchParams();
  return homeSectionFromSearch(params);
}
