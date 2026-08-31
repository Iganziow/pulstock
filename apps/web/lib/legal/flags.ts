/**
 * Interruptores de funciones que dependen del backend.
 *
 * `RECUPERACION_ACTIVA` apaga los enlaces de "Olvidé mi contraseña" mientras
 * el endpoint no exista en producción.
 *
 * Por qué existe: el 30-ago-2026 se desplegó SOLO el frontend, con el backend
 * dos docenas de commits atrás. Las pantallas de recuperación ya estaban
 * construidas y probadas, pero `/api/auth/password/reset/` devolvía 404 —
 * verificado contra el servidor. Un enlace visible que lleva a un error es
 * peor que no tener el enlace, sobre todo cuando la función es justamente la
 * que le permite al dueño tomar posesión de su cuenta.
 *
 * PARA ENCENDERLO: poner `true` acá, después de desplegar el backend. Las
 * páginas /recuperar y /recuperar/nueva ya existen y funcionan; esto solo
 * controla si se enlazan desde los dos logins.
 *
 * Se comprueba con:  curl -X POST https://pulstock.cl/api/auth/password/reset/
 * Debe responder 400 (falta el correo), no 404.
 */
// ENCENDIDO el 31-ago-2026, despues de desplegar el backend.
// Comprobado contra produccion: POST /api/auth/password/reset/ responde 400
// (falta el correo), no 404. El endpoint existe.
export const RECUPERACION_ACTIVA = true;
