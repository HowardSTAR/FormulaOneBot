import { apiAssetUrl } from '../../helpers/api';

export type Avatar = { helmet: string; suit: string; background: string };
export const defaultAvatar: Avatar = { helmet: 'scarlet', suit: 'scarlet', background: 'garage' };
export type AvatarOptions = Record<keyof Avatar, Record<string, string>>;
export function avatarUrl(avatar: Avatar) { return apiAssetUrl('/api/profiles/avatar/v1.png', avatar); }
