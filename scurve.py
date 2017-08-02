import numpy as np
from trajectories import Trajectory, plot_trajectory, PlanningError, EPSILON
from trajectories import ACCELERATION_ID, SPEED_ID, POSITION_ID
from planner import TrajectoryPlanner


class ScurvePlanner(TrajectoryPlanner):

    def __init__(self):
        self.s = 1

    def __scurve_check_possibility(self, q0, q1, v0, v1, v_max, a_max, j_max):
        dv = np.abs(v1 - v0)
        dq = np.abs(q1 - q0)

        time_to_reach_max_a = a_max/j_max
        time_to_set_set_speeds = np.sqrt(dv/j_max)

        Tj = min(time_to_reach_max_a, time_to_set_set_speeds)

        if Tj == time_to_reach_max_a:
            return dq > 0.5*(v0 + v1)*(Tj+dv/a_max)

        elif Tj < time_to_reach_max_a:
            return dq > Tj*(v0+v1)

        else:
            raise PlanningError("Something went wrong")

    def __compute_maximum_speed_reached(self, q0, q1, v0, v1,
                                        v_max, a_max, j_max):
        """
        For explanation look at page 79 of
            'Trajectory planning for automatic machines and robots(2008)'
        """

        # Acceleration period
        if (v_max-v0)*j_max < a_max**2:
            # a_max is not reached
            Tj1 = np.sqrt((v_max-v0)/j_max)
            Ta = 2*Tj1
        else:
            # a_max is reached
            Tj1 = a_max/j_max
            Ta = Tj1 + (v_max-v0)/a_max

        # Deceleration period
        if (v_max-v1)*j_max < a_max**2:
            # a_min is not reached
            Tj2 = np.sqrt((v_max-v1)/j_max)
            Td = 2*Tj2
        else:
            # a_min is reached
            Tj2 = a_max/j_max
            Td = Tj2 + (v_max-v1)/a_max

        Tv = (q1-q0)/v_max - (Ta/2)*(1+v0/v_max)-(Td/2)*(1+v1/v_max)

        if Tv < 0:
            raise PlanningError("Maximum velocity is not reached. "
                                "Failed to plan trajectory")

        return Tj1, Ta, Tj2, Td, Tv

    def __sign_transforms(self, q0, q1, v0, v1, v_max, a_max, j_max):
        v_min = -v_max
        a_min = -a_max
        j_min = -j_max

        vs1 = (self.s+1)/2
        vs2 = (self.s-1)/2

        _q0 = self.s*q0
        _q1 = self.s*q1
        _v0 = self.s*v0
        _v1 = self.s*v1
        _v_max = vs1*v_max + vs2*v_min
        _a_max = vs1*a_max + vs2*a_min
        _j_max = vs1*j_max + vs2*j_min

        print("%f %f %f %f %f %f %f" % (q0, q1, v0, v1, v_max, a_max, j_max))
        print("%f %f %f %f %f %f %f" % (_q0, _q1, _v0,
                                        _v1, _v_max, _a_max, _j_max))

        return _q0, _q1, _v0, _v1, _v_max, _a_max, _j_max

    def __point_sign_transform(self, p):
        new_p = np.zeros(p.shape, dtype=np.float32)

        for i in range(len(p)):
            new_p[i] = p[i] * self.s

        return new_p

    def __compute_maximum_speed_not_reached(self, q0, q1, v0, v1,
                                            v_max, a_max, j_max):
        """
        For explanation look at page 79 of
            'Trajectory planning for automatic machines and robots(2008)'

        Right now assuming that maximum/minimum accelerations is reached
            other case is not treated well. TODO: fix it.
        """

        # Assuming that a_max/a_min is reached
        Tj1 = Tj2 = Tj = a_max/j_max
        Tv = 0

        v = (a_max**2)/j_max
        delta = ((a_max**4)/(j_max**2)) + 2*((v0**2)+(v1**2)) +\
            a_max*(4*(q1-q0)-2*(a_max/j_max)*(v0+v1))

        Ta = (v - 2*v0 + np.sqrt(delta))/(2*a_max)
        Td = (v - 2*v1 + np.sqrt(delta))/(2*a_max)

        if (np.abs(Ta - 2*Tj) < EPSILON) or (np.abs(Td - 2*Tj) < EPSILON):
            raise PlanningError("Maximum acceletaion is not reached. Failed to"
                                " plan trajectory")

        return Tj1, Ta, Tj2, Td, Tv

    def get_trajectory_func(self, Tj1, Ta, Tj2, Td, Tv,
                            q0, q1, v0, v1, v_max, a_max, j_max):
        T = Ta + Td + Tv
        a_lim_a = j_max*Tj1
        a_lim_d = -j_max*Tj2
        v_lim = v0 + (Ta-Tj1)*a_lim_a

        print("a_lim_a: %f\r\na_lim_d: %f" % (a_lim_a, a_lim_d))

        def trajectory(t):
            # Acceleration phase
            if 0 <= t < Tj1:
                a = j_max*t
                v = v0 + j_max*(t**2)/2
                q = q0 + v0*t + j_max*(t**3)/6

            elif Tj1 <= t < Ta - Tj1:
                a = a_lim_a
                v = v0 + a_lim_a*(t-Tj1/2)
                q = q0 + v0*t + a_lim_a*(3*(t**2) - 3*Tj1*t + Tj1**2)/6

            elif Ta-Tj1 <= t < Ta:
                tt = Ta - t

                a = j_max*tt
                v = v_lim - j_max*(tt**2)/2
                q = q0 + (v_lim+v0)*Ta/2 - v_lim*tt + j_max*(tt**3)/6

            # Constant velocity phase
            elif Ta <= t < Ta + Tv:
                a = 0
                v = v_lim
                q = q0 + (v_lim+v0)*Ta/2 + v_lim*(t-Ta)

            # Deceleration phase
            elif T - Td <= t < T-Td+Tj2:
                tt = t-T+Td

                a = -j_max*tt
                v = v_lim - j_max*(tt**2)/2
                q = q1 - (v_lim+v1)*Td/2 + v_lim*tt -\
                    j_max*(tt**3)/6

            elif T-Td+Tj2 <= t < T-Tj2:
                tt = t-T+Td

                a = a_lim_d
                v = v_lim + a_lim_d*(tt-Tj2/2)
                q = q1 - (v_lim+v1)*Td/2 + v_lim*tt +\
                    a_lim_d*(3*(tt**2) - 3*Tj2*tt + Tj2**2)/6

            elif T-Tj2 <= t:
                tt = T-t

                a = -j_max*tt
                v = v1 + j_max*(tt**2)/2
                q = q1 - v1*tt - j_max*(tt**3)/6

            point = np.zeros((3,), dtype=np.float32)
            point[ACCELERATION_ID] = a
            point[SPEED_ID] = v
            point[POSITION_ID] = q

            return self.__point_sign_transform(point)

        return trajectory

    def scurve_profile_no_opt(self, q0, q1, v0, v1, v_max, a_max, j_max):
        if self.__scurve_check_possibility(q0, q1, v0, v1, v_max, a_max, j_max):
            try:
                Tj1, Ta, Tj2, Td, Tv =\
                    self.__compute_maximum_speed_reached(q0, q1, v0, v1,
                                                         v_max, a_max, j_max)
            except PlanningError as e:
                print(e)

                Tj1, Ta, Tj2, Td, Tv =\
                    self.__compute_maximum_speed_not_reached(q0, q1, v0, v1,
                                                             v_max, a_max,
                                                             j_max)

            return np.asarray([Tj1, Ta, Tj2, Td, Tv], dtype=np.float32)

        else:
            raise PlanningError("Trajectory is not feasible")

    def scurve_profile_const_time(self, T, q0, q1, v0, v1, v_max,
                                  a_max, j_max, l=0.9, max_iter=2000):
        _T = 0
        _a_max = a_max
        _it_num = 0
        exceptions_in_row = 0

        while (abs(_T-T) >= EPSILON) and (_a_max >= EPSILON) and\
                (_it_num < max_iter):
            try:
                Tj1, Ta, Tj2, Td, Tv = self.scurve_profile_no_opt(q0, q1, v0,
                                                                  v1,
                                                                  v_max,
                                                                  _a_max,
                                                                  j_max)

                _T = Ta + Td + Tv
                exceptions_in_row = 0

            except PlanningError:
                exceptions_in_row += 1

            _a_max *= l
            _it_num += 1

        if abs(_T-T) >= EPSILON:
            raise PlanningError("Failed to fit trajectory in given time.\r\n"
                                "Exceptions in row: %f\r\n"
                                "Iterations number: %f\r\n"
                                "Current acceleration %f"
                                % (exceptions_in_row, _it_num, _a_max))
        else:
            print("_T: %f, T: %f, dT: %f" % (_T, T, abs(_T-T)))

        return np.asarray([Tj1, Ta, Tj2, Td, Tv], dtype=np.float32)

    def __put_params(self, params_list, params, dof):
        for i in range(params.shape[0]):
            params_list[i][dof] = params[i]

    def __get_dof_time(self, params_list, dof):
        return params_list[1][dof] + params_list[3][dof] + params_list[4][dof]

    def plan_trajectory(self, q0, q1, v0, v1, v_max, a_max, j_max):
        sh = self._check_shape(q0, q1, v0, v1)
        ndof = sh[0]

        T = np.zeros(sh)
        Ta = np.zeros(sh)
        Tj1 = np.zeros(sh)
        Td = np.zeros(sh)
        Tj2 = np.zeros(sh)
        Tv = np.zeros(sh)
        trajectory_funcs = []
        trajectory_params = [Tj1, Ta, Tj2, Td, Tv]

        dq = np.subtract(q1, q0)
        max_displacement_id = np.argmax(np.abs(dq))
        self.s = np.sign(dq[max_displacement_id])
        zipped_args = self.__sign_transforms(q0[max_displacement_id],
                                             q1[max_displacement_id],
                                             v0[max_displacement_id],
                                             v1[max_displacement_id],
                                             v_max, a_max, j_max)

        max_displacement_params = self.scurve_profile_no_opt(*zipped_args)

        self.__put_params(trajectory_params,
                          max_displacement_params,
                          max_displacement_id)

        max_displacement_time = self.__get_dof_time(trajectory_params,
                                                    max_displacement_id)
        T[max_displacement_id] = max_displacement_time

        for _q0, _q1, _v0, _v1, ii in zip(q0, q1, v0, v1, range(ndof)):
            if ii == max_displacement_id:
                continue

            print("Computing %d DOF trajectory" % ii)
            # For sign transforms
            self.s = np.sign(_q1-_q0)

            zipped_args =\
                self.__sign_transforms(_q0, _q1, _v0, _v1, v_max, a_max, j_max)

            # In case if final velocity is non-zero
            # We need to synchronize it in time with the trajectory with
            # the longest execution time
            if _v1 != 0:
                traj_params =\
                    self.scurve_profile_const_time(max_displacement_time,
                                                   *zipped_args)

            # if final velocity is zero we do not need to worry about
            # syncronization
            else:
                traj_params = self.scurve_profile_no_opt(*zipped_args)

            T[ii] = Ta[ii] + Td[ii] + Tv[ii]
            self.__put_params(trajectory_params, traj_params, ii)

        for _T, _Ta, _Td, _Tv, _Tj1, _Tj2, dof in zip(T, Ta, Td, Tv,
                                                      Tj1, Tj2, range(ndof)):
            print("DOF %d params:\r\n\tT: %f\r\n\tTa: %f\r\n\tTj1: %f\r\n\t"
                  "Td: %f\r\n\tTj2: %f\r\n\tTv: %f" %
                  (dof, _T, _Ta, _Tj1, _Td, _Tj2, _Tv))

            tr_func = self.get_trajectory_func(_Tj1, _Ta, _Tj2, _Td, _Tv,
                                               *zipped_args)
            trajectory_funcs.append(tr_func)

        print("The longest trajectory id: %d" % max_displacement_id)
        print("The logest trajectory time: %f" % T[max_displacement_id])
        print("The longest trajectory params: " + str(max_displacement_params))

        tr = Trajectory()
        tr.time = (T[max_displacement_id],)
        tr.trajectory = trajectory_funcs
        tr.dof = ndof

        return tr


if __name__ == "__main__":
    q0 = [-2.]
    q1 = [20.]
    v0 = [0.]
    v1 = [2.]
    v_max = 30.
    a_max = 30.
    j_max = 100.

    p = ScurvePlanner()

    tr = p.plan_trajectory(q0, q1, v0, v1, v_max, a_max, j_max)
    plot_trajectory(tr, 0.01)
