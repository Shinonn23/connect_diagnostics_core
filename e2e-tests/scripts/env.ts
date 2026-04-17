import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

/**
 * อ่าน .env file และตั้งค่า environment variables ที่ยังไม่มีใน process.env
 * @param envPath - path ของ .env file
 * @returns true ถ้า file มีอยู่และอ่านสำเร็จ, false ถ้า file ไม่มี
 */
function applyEnvFile(envPath: string) {
  if (!existsSync(envPath)) {
    return false;
  }

  const content = readFileSync(envPath, 'utf-8');
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    const equalsIndex = trimmed.indexOf('=');
    if (equalsIndex < 0) {
      continue;
    }

    const key = trimmed.slice(0, equalsIndex).trim();
    const rawValue = trimmed.slice(equalsIndex + 1).trim();
    const value = rawValue.replace(/^['"]|['"]$/g, '');

    if (!(key in process.env)) {
      process.env[key] = value;
    }
  }

  return true;
}

/**
 * โหลด local .env file ถ้ามี ถ้าไม่มีจะ fallback ไปอ่าน .env.example แทน
 * @param envPath - path ของ .env file (default: .env ใน working directory)
 */
export function loadLocalEnv(envPath = path.resolve(process.cwd(), '.env')) {
  const loadedPrimary = applyEnvFile(envPath);
  if (loadedPrimary) {
    return;
  }

  applyEnvFile(path.resolve(process.cwd(), '.env.example'));
}
