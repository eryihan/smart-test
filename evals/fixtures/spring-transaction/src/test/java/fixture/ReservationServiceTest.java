package fixture;

import java.util.UUID;
import javax.sql.DataSource;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import static org.junit.Assert.*;

public class ReservationServiceTest {
    private AnnotationConfigApplicationContext context;
    private JdbcTemplate jdbc;
    private ReservationService service;

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean public DataSource dataSource() {
            JdbcDataSource source = new JdbcDataSource();
            source.setURL("jdbc:h2:mem:" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1");
            return source;
        }
        @Bean public JdbcTemplate jdbc(DataSource source) { return new JdbcTemplate(source); }
        @Bean public PlatformTransactionManager transactions(DataSource source) {
            return new DataSourceTransactionManager(source);
        }
        @Bean public ReservationService service(JdbcTemplate jdbc) { return new ReservationService(jdbc); }
    }

    @Before public void setup() {
        context = new AnnotationConfigApplicationContext(Config.class);
        jdbc = context.getBean(JdbcTemplate.class);
        service = context.getBean(ReservationService.class);
        jdbc.execute("CREATE TABLE inventory(id INT PRIMARY KEY, available INT NOT NULL)");
        jdbc.execute("CREATE TABLE reservation(order_id VARCHAR(40) PRIMARY KEY, quantity INT NOT NULL)");
        jdbc.update("INSERT INTO inventory VALUES (1, 10)");
    }

    @After public void cleanup() {
        if (jdbc != null) { jdbc.execute("DROP ALL OBJECTS"); }
        if (context != null) { context.close(); }
    }

    @Test public void successfulReservationPersistsBothChanges() {
        service.reserve("order-1", 3);
        assertEquals(7, available());
        assertEquals(Integer.valueOf(3), jdbc.queryForObject(
                "SELECT quantity FROM reservation WHERE order_id = ?", Integer.class, "order-1"));
    }

    // The test itself has no transaction: reads observe the service transaction's commit or rollback.
    @Test public void duplicateOrderRollsBackStockDeduction() {
        service.reserve("order-1", 3);
        try {
            service.reserve("order-1", 2);
            fail("duplicate order must be rejected");
        } catch (DataIntegrityViolationException expected) {
            assertEquals(7, available());
            assertEquals(1, reservations());
            assertEquals(Integer.valueOf(3), jdbc.queryForObject(
                    "SELECT quantity FROM reservation WHERE order_id = ?", Integer.class, "order-1"));
        }
    }

    @Test public void insufficientStockPreservesInventoryAndReservations() {
        try {
            service.reserve("order-1", 11);
            fail("insufficient stock must be rejected");
        } catch (IllegalStateException expected) {
            assertEquals(10, available());
            assertEquals(0, reservations());
        }
    }

    @Test public void nonpositiveQuantityDoesNotWriteData() {
        for (int quantity : new int[] {0, -1}) {
            try {
                service.reserve("order-1", quantity);
                fail("nonpositive quantity must be rejected");
            } catch (IllegalArgumentException expected) {
                assertEquals(10, available());
                assertEquals(0, reservations());
            }
        }
    }

    @Test public void serviceIsObtainedThroughTransactionProxy() {
        assertTrue("service must use the Spring transaction proxy", AopUtils.isAopProxy(service));
    }

    private int available() {
        return jdbc.queryForObject("SELECT available FROM inventory WHERE id = 1", Integer.class);
    }
    private int reservations() {
        return jdbc.queryForObject("SELECT COUNT(*) FROM reservation", Integer.class);
    }
}
