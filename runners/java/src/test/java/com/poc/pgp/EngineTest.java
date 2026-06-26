package com.poc.pgp;

/**
 * เทสต์ของน้อง — เขียนเอง
 *
 * อย่างน้อยต้องครอบคลุม:
 *   1) round-trip ของ InMemoryEngine: encrypt แล้ว decrypt ได้ byte เดิมเป๊ะ
 *   2) round-trip ของ StreamingEngine: เช่นเดียวกัน
 *   3) ไฟล์ว่าง (0 byte) round-trip ได้ ไม่ crash
 *   (เสริม) ไฟล์ใหญ่กับ StreamingEngine แล้วยืนยันว่า peak memory ไม่โตตามไฟล์
 *
 * ใช้กุญแจจริงจากโฟลเดอร์ keys/ ของโปรเจกต์ (เช่น path "../../keys")
 *
 * TODO(น้อง): เขียนเทสต์จริงด้วย JUnit 5
 */
public class EngineTest {
}
