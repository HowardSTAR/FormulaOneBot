import { useEffect, useId, useRef, useState } from 'react';
import { DriverPortrait } from '../../components/DriverPortrait';
import { TeamLogo } from '../../components/TeamLogo';
import { homeTeamIdentity } from '../index/team-identity';
import { hapticSelection } from '../../helpers/telegram';
import './participant-picker.css';

export type ComparisonOption = { code: string; name: string; team?: string; imageUrl?: string };

export function CompareParticipantPicker({ options, season, teamMode, onAdd, onClose }: {
  options: ComparisonOption[]; season: number; teamMode: boolean;
  onAdd: (codes: string[]) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useId();
  const searchId = useId();
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const filtered = options.filter(option => `${option.name} ${option.code} ${option.team || ''}`.toLocaleLowerCase('ru').includes(search.trim().toLocaleLowerCase('ru')));
  const selectedSet = new Set(selected);
  const allVisibleSelected = filtered.length > 0 && filtered.every(option => selectedSet.has(option.code));

  useEffect(() => {
    const element = dialog.current!;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    element.showModal();
    // Start on the title so opening the sheet never summons a mobile keyboard.
    element.querySelector<HTMLElement>('h2')?.focus();
    return () => { element.close(); document.body.style.overflow = previousOverflow; };
  }, []);

  const toggle = (code: string) => {
    hapticSelection();
    setSelected(current => current.includes(code) ? current.filter(value => value !== code) : [...current, code]);
  };
  const toggleVisible = () => {
    hapticSelection();
    const visible = new Set(filtered.map(option => option.code));
    setSelected(current => allVisibleSelected ? current.filter(code => !visible.has(code)) : [...new Set([...current, ...visible])]);
  };

  return <dialog ref={dialog} className="comparison-choice" aria-labelledby={title}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === event.currentTarget) {
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    } }}>
    <header className="comparison-choice-header">
      <h2 id={title} tabIndex={-1}>{teamMode ? 'Выберите команды' : 'Выберите пилотов'}</h2>
      <button type="button" className="comparison-choice-close" aria-label="Закрыть выбор участников" onClick={onClose}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
    </header>
    <div className="comparison-choice-search">
      <label htmlFor={searchId}>{teamMode ? 'Поиск команды' : 'Поиск пилота'}</label>
      <div><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg><input id={searchId} type="search" name="participants" autoComplete="off" placeholder={teamMode ? 'Название команды…' : 'Имя, код или команда…'} value={search} onChange={event => setSearch(event.target.value)} /></div>
    </div>
    <div className="comparison-choice-tools">
      <button type="button" disabled={!filtered.length} onClick={toggleVisible}>{allVisibleSelected ? 'Снять отметки' : search.trim() ? 'Выбрать найденных' : 'Выбрать всех'}</button>
      <span role="status">{filtered.length} из {options.length}</span>
    </div>
    <div className="comparison-choice-list" role="group" aria-label={teamMode ? 'Доступные команды' : 'Доступные пилоты'}>
      {!filtered.length && <p className="comparison-choice-empty" role="status">Ничего не найдено. Измените поисковый запрос.</p>}
      {filtered.map(option => <label key={option.code} className="comparison-choice-option entrant-highlight" data-team={homeTeamIdentity('', teamMode ? option.name : option.team || '')} data-selected={selectedSet.has(option.code) || undefined}>
        {teamMode ? <TeamLogo key={`${season}:${option.code}`} name={option.name} season={season} /> : <DriverPortrait key={`${season}:${option.code}`} code={option.code} name={option.name} src={option.imageUrl} season={season} />}
        <span className="comparison-choice-name"><strong>{option.name}</strong><small>{teamMode ? `Сезон ${season}` : option.team || option.code}</small></span>
        <input type="checkbox" aria-label={option.name} checked={selectedSet.has(option.code)} onChange={() => toggle(option.code)} />
        <span className="comparison-choice-check" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 4 4L19 6" /></svg></span>
      </label>)}
    </div>
    <footer className="comparison-choice-footer">
      <div><span role="status">Выбрано: <strong>{selected.length}</strong></span><button type="button" className="comparison-choice-reset" aria-label="Сбросить выбор" title="Сбросить выбор" disabled={!selected.length} onClick={() => setSelected([])}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 4v5h5M3 9a9 9 0 1 1 0 6" /></svg></button></div>
      <button type="button" className="comparison-choice-apply" disabled={!selected.length} onClick={() => onAdd(selected)}>Добавить{selected.length > 0 ? ` (${selected.length})` : ''}</button>
    </footer>
  </dialog>;
}
