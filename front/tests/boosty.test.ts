import test from 'node:test';
import assert from 'node:assert/strict';
import { boostySubscriptionLabel, type BoostyStatus } from '../src/helpers/boosty.ts';

const status: BoostyStatus = {
  eligible: true, configured: true, active: true, blog_url: 'https://boosty.to/turbotears',
  level_name: 'Полный газ', checked_at: 1791720000, check_failed: false,
  premium_active: true, premium_override: null, expires_at: Date.parse('2026-11-11T12:00:00Z') / 1000,
  can_check: true, check_unavailable_reason: null,
};

test('subscription shows its actual level and paid end date', () => {
  assert.equal(boostySubscriptionLabel(status), 'Подписка «Полный газ» активна до 11.11.2026.');
});

test('unknown expiry is explicit and never replaced by a made-up date', () => {
  assert.equal(boostySubscriptionLabel({ ...status, expires_at: null }), 'Подписка «Полный газ» активна. Boosty не передал дату окончания.');
});

test('expired and missing subscriptions do not look active', () => {
  assert.equal(boostySubscriptionLabel({ ...status, active: false }, Date.parse('2026-11-12T12:00:00Z')), 'Подписка закончилась 11.11.2026.');
  assert.equal(boostySubscriptionLabel({ ...status, active: false, expires_at: null }), 'Активная платная подписка не найдена.');
  assert.equal(boostySubscriptionLabel({ ...status, active: false, expires_at: null, checked_at: null }), 'Подписка ещё не проверена.');
});
