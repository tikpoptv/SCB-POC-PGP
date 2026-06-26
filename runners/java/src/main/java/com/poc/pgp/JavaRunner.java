package com.poc.pgp;

/**
 * Java PGP Runner — จุดเริ่มของโปรแกรม (CLI)
 * ---------------------------------------------------------------------------
 * โครงนี้ตั้งใจเว้นไว้ให้น้อง "เขียนเอง" เพื่อให้ได้ฝึก
 *
 * สิ่งที่ main() ต้องทำ (ออกแบบรายละเอียดเอง):
 *   1) อ่านคำสั่ง JSON จาก stdin  (ดูสัญญาใน docs/handoff-java-inmem-variant.md)
 *   2) เลือก engine ตาม variantId: "java-inmem-single" หรือ "java-stream-single"
 *   3) วนทุกไฟล์ใน corpusPath:
 *        - ถ้าเป็น .ctrl/.ctl -> ข้าม (skipped=true)
 *        - ไม่งั้น encrypt -> เขียนไฟล์ .pgp -> decrypt -> เทียบ byte-for-byte
 *        - จับเวลาเฉพาะ encrypt/decrypt (ห้ามรวม I/O และโหลดกุญแจ)
 *   4) พิมพ์ผลรวมเป็น JSON ออก stdout (log ออก stderr เท่านั้น)
 *
 * ไลบรารีที่มีให้ใน pom.xml แล้ว: Bouncy Castle (bcpg/bcprov), Jackson (JSON), JUnit
 */
public class JavaRunner {

    public static void main(String[] args) throws Exception {
        // TODO(น้อง): implement ตามขั้นตอนด้านบน
        throw new UnsupportedOperationException("JavaRunner.main: ยังไม่ทำ");
    }
}
