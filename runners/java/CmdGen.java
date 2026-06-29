import com.poc.pgp.Checksum;
import java.nio.file.Path;
import java.nio.file.Paths;

// Throwaway single-file helper: prints a Command JSON with real checksums so the
// native binary's checksum gate passes. Run with: java -cp target/classes CmdGen.java <keys> <corpus> <out> <pubAlg> <op>
public class CmdGen {
    public static void main(String[] a) throws Exception {
        Path keys = Paths.get(a[0]).toAbsolutePath().normalize();
        Path corpus = Paths.get(a[1]).toAbsolutePath().normalize();
        Path out = Paths.get(a[2]).toAbsolutePath().normalize();
        String pubAlg = a[3];
        String op = a[4];
        String ks = Checksum.computeKeySetChecksum(keys);
        String cs = Checksum.computeCorpusChecksum(corpus);
        System.out.print("{"
            + "\"command\":\"run\",\"variantId\":\"java-native-stream-parallel\",\"mode\":\"steady_state\","
            + "\"warmupIterations\":0,\"concurrency\":2,"
            + "\"cryptoProfile\":{\"pubAlg\":\"" + pubAlg + "\",\"cipher\":\"AES-256\",\"compression\":\"ZLIB\",\"hash\":\"SHA-256\"},"
            + "\"outputEncoding\":\"binary\","
            + "\"keySetPath\":\"" + j(keys.toString()) + "\",\"keySetChecksum\":\"" + ks + "\","
            + "\"corpusPath\":\"" + j(corpus.toString()) + "\",\"corpusChecksum\":\"" + cs + "\","
            + "\"outputDir\":\"" + j(out.toString()) + "\",\"operation\":\"" + op + "\"}");
    }
    static String j(String s) { return s.replace("\\", "\\\\").replace("\"", "\\\""); }
}
