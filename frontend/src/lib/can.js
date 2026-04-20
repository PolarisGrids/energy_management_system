/**
 * Capability-check helpers for Polaris EMS RBAC (spec 015-rbac-ui-lib).
 *
 * Permissions are dotted strings (e.g. ``users.manage``). They are embedded
 * in the JWT as the ``perm`` claim at login and mirrored onto the auth
 * store's ``user.permissions`` array for fast render-time checks.
 */

/**
 * Return true iff the user has the given capability.
 *
 * @param {{permissions?: string[]}|null|undefined} user
 * @param {string} capName
 * @returns {boolean}
 */
export function can(user, capName) {
  if (!user || !capName) return false
  const perms = user.permissions || []
  return Array.isArray(perms) && perms.includes(capName)
}

/**
 * Return true iff the user has ANY of the listed capabilities.
 */
export function canAny(user, ...capNames) {
  if (!user || !capNames.length) return false
  const perms = user.permissions || []
  return capNames.some((c) => perms.includes(c))
}

/**
 * Return true iff the user has ALL of the listed capabilities.
 */
export function canAll(user, ...capNames) {
  if (!user || !capNames.length) return false
  const perms = user.permissions || []
  return capNames.every((c) => perms.includes(c))
}

/**
 * Decode the ``perm`` claim from a JWT without validating signature.
 * Used when bootstrapping from localStorage.
 */
export function decodePermsFromJWT(token) {
  if (!token || typeof token !== 'string') return []
  try {
    const parts = token.split('.')
    if (parts.length < 2) return []
    const payload = JSON.parse(
      atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))
    )
    return Array.isArray(payload?.perm) ? payload.perm : []
  } catch {
    return []
  }
}
